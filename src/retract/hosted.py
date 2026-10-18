"""Public workspace boundary: verified identities, separate graphs, revocable keys.

One application replica owns the database. Never use caller-supplied project IDs
or headers as tenant identities. Local mode does not instantiate this module.
"""
from collections import OrderedDict
from dataclasses import dataclass
import base64
import hashlib
import json
import os
import re
import secrets
from threading import RLock
import time
from urllib.parse import urlsplit

from .graph import GraphStore
from .models import ValidationError, text
from .service import MemoryService


class AccessError(Exception):
    def __init__(self, message="Sign in to continue", status=401):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class HostedConfig:
    origin: str
    issuer: str
    publishable_key: str
    graph_prefix: str = "retract_hosted"

    def __post_init__(self):
        for value in (self.origin, self.issuer):
            parsed = urlsplit(value)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.path or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
                raise ValueError("Hosted URLs must be HTTPS origins without a trailing slash")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", self.graph_prefix):
            raise ValueError("Invalid hosted graph prefix")
        try:
            encoded = self.publishable_key.split("_", 2)[2]
            domain = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True).decode()
            if not self.publishable_key.startswith(("pk_test_", "pk_live_")) or domain != urlsplit(self.issuer).netloc + "$":
                raise ValueError()
        except (ValueError, IndexError, UnicodeError):
            raise ValueError("Clerk publishable key must match CLERK_ISSUER_URL") from None

    @classmethod
    def from_env(cls):
        if not os.getenv("CLERK_WEBHOOK_SECRET"):
            raise ValueError("Set CLERK_WEBHOOK_SECRET for account deletion and key revocation")
        return cls(os.environ["RETRACT_PUBLIC_URL"], os.environ["CLERK_ISSUER_URL"],
                   os.environ["CLERK_PUBLISHABLE_KEY"], os.getenv("RETRACT_GRAPH_PREFIX", "retract_hosted"))

    def public(self):
        return {"mode": "hosted", "publishable_key": self.publishable_key, "issuer": self.issuer,
                "origin": self.origin}

    def csp(self):
        # Clerk's UI requires inline styles; application scripts stay external.
        return (f"default-src 'self'; script-src 'self' {self.issuer} https://challenges.cloudflare.com; "
                f"connect-src 'self' {self.issuer}; style-src 'self' 'unsafe-inline'; "
                f"img-src 'self' data: {self.issuer} https://img.clerk.com; font-src 'self' {self.issuer}; "
                f"frame-src {self.issuer} https://challenges.cloudflare.com; worker-src 'self' blob:; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


class ClerkVerifier:
    def __init__(self, config):
        import jwt
        self.config = config
        import ssl
        import certifi
        self.jwks = jwt.PyJWKClient(config.issuer + "/.well-known/jwks.json", timeout=5, lifespan=300,
                                    ssl_context=ssl.create_default_context(cafile=certifi.where()))

    def verify(self, token):
        import jwt
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], issuer=self.config.issuer,
                                options={"require": ["exp", "nbf", "iat", "iss", "sub", "sid", "azp"]}, leeway=5)
            if (claims.get("azp") != self.config.origin or claims.get("sts") == "pending"
                    or not isinstance(claims["sub"], str) or not claims["sub"].startswith("user_")
                    or not isinstance(claims["sid"], str) or not claims["sid"].startswith("sess_")):
                raise AccessError()
            return claims["sub"]
        except AccessError:
            raise
        except jwt.PyJWKClientConnectionError:
            raise AccessError("Authentication provider unavailable. Retry shortly.", 503) from None
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise AccessError("Session expired or invalid. Sign in again.") from None


class RateLimit:
    def __init__(self):
        self.buckets = OrderedDict()
        self.lock = RLock()

    def check(self, key, maximum, period=60):
        now = time.monotonic()
        with self.lock:
            start, count = self.buckets.pop(key, (now, 0))
            if now - start >= period:
                start, count = now, 0
            self.buckets[key] = (start, count + 1)
            while len(self.buckets) > 10000:
                self.buckets.popitem(last=False)
            if count >= maximum:
                raise AccessError("Request limit reached. Retry in one minute.", 429)


class HostedWorkspaces:
    def __init__(self, config, root_store, verifier=None):
        self.config = config
        self.root = root_store
        self.lock = RLock()
        self.verifier = verifier or ClerkVerifier(config)
        self.limits = RateLimit()
        self.services = OrderedDict()
        self.auth = GraphStore(root_store.client.select_graph(config.graph_prefix + "_access"))
        self.auth.initialize()

    def owner_id(self, subject):
        return hashlib.sha256((self.config.issuer + "\0" + subject).encode()).hexdigest()

    def identity(self, headers):
        values = headers.get_all("Authorization", [])
        if len(values) != 1 or not values[0].startswith("Bearer ") or len(values[0]) > 16384:
            raise AccessError()
        token = values[0][7:]
        if token.startswith("rt_"):
            if not re.fullmatch(r"rt_[A-Za-z0-9_-]{43}", token):
                raise AccessError("Invalid access key")
            digest = hashlib.sha256(token.encode()).hexdigest()
            rows = self.auth.query("MATCH (k:AccessKey {digest: $digest}) WHERE k.revoked = false AND k.expires_at > $now RETURN k.owner", {"digest": digest, "now": int(time.time())})
            if len(rows) != 1:
                raise AccessError("Access key expired or revoked")
            return rows[0][0], "key"
        subject = self.verifier.verify(token)
        owner = self.owner_id(subject)
        if self.auth.query("MATCH (a:DeletedAccount {owner: $owner}) RETURN a.owner", {"owner": owner}):
            raise AccessError("This account has been deleted")
        return owner, "session"

    def service(self, owner):
        with self.lock:
            service = self.services.pop(owner, None)
            if service is None:
                store = GraphStore(self.root.client.select_graph(self.config.graph_prefix + "_" + owner))
                store.initialize()
                service = MemoryService(store)
                service.lock = self.lock
            self.services[owner] = service
            while len(self.services) > 128:
                self.services.popitem(last=False)
            return service

    def keys(self, owner):
        rows = self.auth.query("MATCH (k:AccessKey {owner: $owner}) WHERE k.revoked = false AND k.expires_at > $now RETURN k.id, k.name, k.created_at, k.expires_at ORDER BY k.created_at DESC", {"owner": owner, "now": int(time.time())})
        return {"keys": [dict(zip(("id", "name", "created_at", "expires_at"), row)) for row in rows]}

    def manage(self, path, body, owner, kind):
        if kind != "session":
            raise AccessError("Sign in through the dashboard to manage access keys", 403)
        with self.lock:
            if path == "/account/export":
                if body:
                    raise ValidationError("Export does not accept parameters")
                store = self.service(owner).store
                nodes = store.query("MATCH (n) RETURN id(n), labels(n), properties(n)", {})
                edges = store.query("MATCH (a)-[r]->(b) RETURN id(a), type(r), id(b)", {})
                result = {"format": "retract-workspace-v1", "exported_at": int(time.time()), "nodes": nodes, "edges": edges}
                if len(json.dumps(result).encode()) > 16 * 1024 * 1024:
                    raise AccessError("Export exceeds 16 MiB. Contact the operator for a database export.", 413)
                return result
            if path == "/account/clear":
                if body != {"confirmation": "DELETE MY WORKSPACE"}:
                    raise ValidationError("Type DELETE MY WORKSPACE to confirm")
                self.clear(owner)
                return {"status": "deleted"}
            if path == "/account/keys":
                if set(body) != {"name"}:
                    raise ValidationError("Supply an access key name")
                text(body["name"], "name", 100)
                if len(self.keys(owner)["keys"]) >= 10:
                    raise AccessError("Revoke an existing key before creating another (limit 10)", 409)
                token = "rt_" + secrets.token_urlsafe(32)
                key = {"id": secrets.token_hex(16), "name": body["name"], "owner": owner,
                       "digest": hashlib.sha256(token.encode()).hexdigest(), "revoked": False,
                       "created_at": int(time.time()), "expires_at": int(time.time()) + 90 * 86400}
                self.auth.query("CREATE (k:AccessKey) SET k = $key RETURN k.id", {"key": key}, write=True)
                return {"id": key["id"], "token": token, "expires_at": key["expires_at"]}
            if path == "/account/keys/revoke":
                if set(body) != {"id"} or not isinstance(body["id"], str):
                    raise ValidationError("Supply the access key ID")
                self.auth.query("MATCH (k:AccessKey {owner: $owner, id: $id}) SET k.revoked = true RETURN k.id", {"owner": owner, "id": body["id"]}, write=True)
                return {"status": "revoked"}
        raise ValidationError("Unknown account operation")

    def clear(self, owner, *, account_deleted=False):
        with self.lock:
            self.auth.query("MATCH (k:AccessKey {owner: $owner}) SET k.revoked = true RETURN k.id", {"owner": owner}, write=True)
            if account_deleted:
                self.auth.query("MERGE (a:DeletedAccount {owner: $owner}) SET a.deleted_at = $now RETURN a.owner", {"owner": owner, "now": int(time.time())}, write=True)
            service = self.service(owner)
            service.store.query("MATCH (n) DETACH DELETE n", {}, write=True)
            self.services.pop(owner, None)

    def webhook(self, raw, headers):
        from svix.webhooks import Webhook, WebhookVerificationError
        secret = os.getenv("CLERK_WEBHOOK_SECRET")
        if not secret:
            raise AccessError("Account webhook is not configured", 503)
        try:
            event = Webhook(secret).verify(raw.decode(), dict(headers.items()))
        except (WebhookVerificationError, UnicodeError, ValueError):
            raise AccessError("Invalid webhook signature", 400) from None
        if event.get("type") == "user.deleted":
            subject = event.get("data", {}).get("id")
            if not isinstance(subject, str) or not subject.startswith("user_"):
                raise ValidationError("Missing deleted user ID")
            self.clear(self.owner_id(subject), account_deleted=True)
        return {"status": "received"}

    def quota(self, service, route):
        limits = {"/projects": ("Project", 25), "/remember": ("Fact", 5000),
                  "/plans": ("Plan", 2000), "/plans/revise": ("Plan", 2000), "/handoffs": ("Handoff", 2000),
                  "/updates": ("UpdateEvent", 10000), "/updates/natural": ("UpdateEvent", 10000)}
        if route in limits:
            label, maximum = limits[route]
            count = service.store.query(f"MATCH (n:{label}) RETURN count(n)", {})[0][0]
            if count >= maximum:
                raise AccessError("Workspace storage limit reached. Contact the operator.", 409)
