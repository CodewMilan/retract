"""Small local JSON adapter. Run one process; all writes share MemoryService.lock."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import re
from importlib.resources import files
from time import monotonic
from urllib.parse import urlsplit

from .graph import DatabaseUnavailable
from .hosted import AccessError
from .landing_pages import LANDING_CSP, landing_asset, warn_missing_landing
from .inference import ModelRateLimited, ModelResponseError, ModelUnavailable
from .models import (
    ClaimInput, ConflictError, HandoffInput, NaturalUpdateInput, NotFoundError, PlanInput, PlanRevisionInput,
    RememberInput, UpdateInput, ValidationError, parse,
)
from .service import MemoryService


MAX_BODY = 65536
logger = logging.getLogger(__name__)
_FONT = re.compile(r"[a-z0-9-]+\.woff2\Z")
LOCAL_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
_CLERK_IMG = (
    "https://img.clerk.com https://images.clerk.dev https://*.googleusercontent.com https://avatars.githubusercontent.com"
)


def local_clerk():
    """Public Clerk fields for the local sign-in page. Absent when the keys are unset."""
    key = os.getenv("CLERK_PUBLISHABLE_KEY", "").strip()
    issuer = os.getenv("CLERK_ISSUER_URL", "").strip().rstrip("/")
    parsed = urlsplit(issuer) if issuer else None
    if not key.startswith(("pk_test_", "pk_live_")) or parsed is None or parsed.scheme != "https" or not parsed.hostname:
        return None
    return {"publishable_key": key, "issuer": issuer}


def clerk_page_policy(issuer):
    return (f"default-src 'self'; script-src 'self' {issuer} https://challenges.cloudflare.com; "
            f"connect-src 'self' {issuer}; style-src 'self' 'unsafe-inline'; "
            f"img-src 'self' data: blob: {issuer} {_CLERK_IMG}; font-src 'self' {issuer}; "
            f"frame-src {issuer} https://challenges.cloudflare.com; worker-src 'self' blob:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


def landing_clerk_policy(issuer):
    """Marketing page policy once Clerk is configured. Keeps the landing fonts and adds account images."""
    return ("default-src 'self'; "
            f"script-src 'self' {issuer} https://challenges.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            f"font-src 'self' https://fonts.gstatic.com {issuer}; "
            f"img-src 'self' data: blob: {issuer} {_CLERK_IMG}; "
            f"connect-src 'self' {issuer}; "
            f"frame-src {issuer} https://challenges.cloudflare.com; worker-src 'self' blob:; "
            "mask-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


def configured_issuer(hosted):
    if hosted is not None:
        issuer = getattr(hosted.config, "issuer", "")
        parsed = urlsplit(issuer) if isinstance(issuer, str) else None
        if parsed is None or parsed.scheme != "https" or not parsed.hostname:
            return None
        return issuer.rstrip("/")
    found = local_clerk()
    return found["issuer"] if found else None


def font_bytes(name):
    if not _FONT.fullmatch(name):
        return None
    path = files("retract").joinpath("web", "fonts", name)
    return path.read_bytes() if path.is_file() else None


def dispatch(service: MemoryService, path: str, body: dict) -> dict:
    if path == "/dashboard":
        if "project_id" not in body or set(body) - {"project_id", "scope"}:
            raise ValidationError("Supply project_id and optional scope")
        return service.dashboard(**body)
    if path == "/projects":
        if set(body) != {"project_id", "name"}:
            raise ValidationError("Supply project_id and name")
        return service.create_project(**body)
    if path == "/remember":
        return service.remember(parse(RememberInput, body))
    if path == "/updates":
        return service.process_update(parse(UpdateInput, body))
    if path == "/updates/natural":
        return service.process_natural_update(parse(NaturalUpdateInput, body))
    if path == "/plans":
        return service.record_plan(parse(PlanInput, body))
    if path == "/plans/revise":
        return service.revise_plan(parse(PlanRevisionInput, body))
    if path == "/handoffs":
        return service.create_handoff(parse(HandoffInput, body))
    if path == "/handoffs/claim":
        return service.claim_handoff(parse(ClaimInput, body))
    if path == "/recall":
        if not {"project_id", "scope"} <= body.keys() or set(body) - {"project_id", "scope", "subjects"}:
            raise ValidationError("Supply project_id, scope, and optional subjects")
        return service.recall(**body)
    if path == "/analyze":
        if not {"project_id", "tool"} <= body.keys() or set(body) - {"project_id", "tool", "args"}:
            raise ValidationError("Supply project_id, tool, and optional args")
        return service.analyze(**body)
    if path == "/history":
        if "project_id" not in body or set(body) - {"project_id", "fact_id", "event_id"}:
            raise ValidationError("Supply project_id and either fact_id or event_id")
        return service.history(**body)
    raise NotFoundError("Unknown API route")


def make_handler(service: MemoryService, hosted=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RETRACT/0.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            # Source text and request bodies are deliberately absent from logs.
            logger.info(format, *args)

        def respond(self, status: int, result: dict, retry_after: int | None = None):
            self.response_status = status
            encoded = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            if retry_after is not None:
                self.send_header("Retry-After", str(retry_after))
            self.end_headers()
            self.wfile.write(encoded)
            self.close_connection = True

        def send_static(self, encoded, mime, cache, policy):
            self.send_response(200)
            charset = "; charset=utf-8" if mime.startswith("text/") else ""
            self.send_header("Content-Type", mime + charset)
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", policy)
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(encoded)
            self.close_connection = True

        def content_policy(self):
            issuer = configured_issuer(hosted)
            bare = self.path.split("?", 1)[0]
            if bare == "/":
                return landing_clerk_policy(issuer) if issuer else LANDING_CSP
            if issuer and bare in {"/dashboard", "/sso-callback"}:
                return clerk_page_policy(issuer)
            if hosted:
                return hosted.config.csp()
            return LOCAL_CSP

        def valid_origin(self):
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            origin = self.headers.get("Origin")
            if len(self.headers.get_all("Host", [])) != 1 or len(self.headers.get_all("Origin", [])) > 1:
                return False
            if hosted:
                public_host = urlsplit(hosted.config.origin).netloc
                if self.path == "/health" and origin is None:
                    return True
                return self.headers.get("Host") == public_host and origin in (None, hosted.config.origin)
            try:
                return self.headers.get("Host") in allowed and (
                    origin is None or (urlsplit(origin).scheme == "http" and urlsplit(origin).netloc in allowed)
                )
            except ValueError:
                return False

        def workspace(self):
            if hosted is None:
                return service
            hosted.limits.check(("ip", self.client_address[0]), 1200)
            owner, kind = hosted.identity(self.headers)
            hosted.limits.check(("owner", owner), 120)
            self.owner, self.identity_kind = owner, kind
            return hosted.service(owner)

        def do_GET(self):
            if not self.valid_origin():
                self.respond(403, {"error": "Local origin required"})
                return
            try:
                if self.path.startswith("/assets/fonts/"):
                    encoded = font_bytes(self.path.removeprefix("/assets/fonts/"))
                    if encoded is None:
                        self.respond(404, {"error": "Unknown API route"})
                        return
                    self.send_static(encoded, "font/woff2", "public, max-age=86400", self.content_policy())
                    return
                if self.path == "/api/config":
                    if hosted:
                        self.respond(200, hosted.config.public())
                    else:
                        body = {"mode": "local"}
                        clerk = local_clerk()
                        if clerk:
                            body.update(clerk)
                        self.respond(200, body)
                    return
                # / is the marketing page in every mode. The workspace is /dashboard.
                if self.path == "/":
                    landing = landing_asset("/")
                    if landing is not None:
                        self.send_static(*landing, self.content_policy())
                        return
                    warn_missing_landing()
                    self.respond(404, {"error": "Landing build is missing. The workspace is at /dashboard."})
                    return
                assets = {"/dashboard": ("index.html", "text/html"),
                          "/assets/dashboard.css": ("dashboard.css", "text/css"),
                          "/assets/dashboard.mjs": ("dashboard.mjs", "text/javascript"),
                          "/assets/dashboard-model.mjs": ("dashboard-model.mjs", "text/javascript"),
                          "/assets/auth.mjs": ("auth.mjs", "text/javascript"),
                          "/assets/auth-portrait.mjs": ("auth-portrait.mjs", "text/javascript"),
                          "/assets/gsap.min.js": ("gsap.min.js", "text/javascript"),
                          "/assets/loader.mjs": ("loader.mjs", "text/javascript")}
                # Workspace filters live in the URL so a saved link survives reload.
                # OAuth returns to /sso-callback, which must be this same page so the session can finish.
                bare = self.path.split("?", 1)[0]
                asset_path = "/dashboard" if bare in {"/dashboard", "/sso-callback"} else self.path
                if asset_path in assets:
                    name, mime = assets[asset_path]
                    encoded = files("retract").joinpath("web", name).read_bytes()
                    self.send_static(encoded, mime, "no-store", self.content_policy())
                    return
                landing = landing_asset(self.path)
                if landing is not None:
                    self.send_static(*landing, self.content_policy())
                    return
                if self.path == "/api/projects":
                    self.respond(200, self.workspace().list_projects())
                    return
                if self.path == "/api/keys" and hosted:
                    self.workspace()
                    if self.identity_kind != "session":
                        raise AccessError("Sign in to manage access keys", 403)
                    self.respond(200, hosted.keys(self.owner))
                    return
                if self.path != "/health":
                    self.respond(404, {"error": "Unknown API route"})
                    return
                with service.lock:
                    service.store.query("RETURN 1", {})
                self.respond(200, {"status": "ok", "storage": "falkordb"})
            except AccessError as exc:
                self.respond(exc.status, {"error": str(exc)}, 60 if exc.status == 429 else None)
            except DatabaseUnavailable as exc:
                self.respond(503, {"error": str(exc)})
            except Exception:
                logger.exception("Unexpected read failure")
                self.respond(500, {"error": "Internal service error"})

        def do_POST(self):
            started = monotonic()
            body = {}
            active_service = None
            self.response_status = 500
            try:
                if not self.valid_origin():
                    self.respond(403, {"error": "Local origin required"})
                    return
                webhook = hosted is not None and self.path == "/webhooks/clerk"
                if webhook:
                    hosted.limits.check(("webhook", self.client_address[0]), 120)
                else:
                    active_service = self.workspace()
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    self.respond(415, {"error": "Content-Type must be application/json"})
                    return
                if self.headers.get("Transfer-Encoding"):
                    raise ValidationError("Transfer-Encoding is unsupported; supply Content-Length")
                if len(self.headers.get_all("Content-Length", [])) > 1:
                    raise ValidationError("Supply exactly one Content-Length header")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    self.respond(413, {"error": f"Body must contain 1–{MAX_BODY} bytes"})
                    return
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValidationError("Incomplete request body")
                if webhook:
                    self.respond(200, hosted.webhook(raw, self.headers))
                    return
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValidationError("Request must be a JSON object")
                if hosted:
                    if self.path.startswith("/account/"):
                        self.respond(200, hosted.manage(self.path, body, self.owner, self.identity_kind))
                        return
                    if self.path == "/updates/natural":
                        hosted.limits.check(("natural", self.owner), 5)
                    with hosted.lock:
                        hosted.quota(active_service, self.path)
                        result = dispatch(active_service, self.path, body)
                else:
                    result = dispatch(active_service, self.path, body)
                self.respond(200, result)
            except AccessError as exc:
                self.respond(exc.status, {"error": str(exc)}, 60 if exc.status == 429 else None)
            except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                self.respond(400, {"error": str(exc)})
            except ConflictError as exc:
                self.respond(409, {"error": str(exc)})
            except NotFoundError as exc:
                self.respond(404, {"error": str(exc)})
            except ModelRateLimited as exc:
                self.respond(429, {"error": str(exc), "retry_after_seconds": exc.retry_after}, exc.retry_after)
            except ModelResponseError as exc:
                self.respond(502, {"error": str(exc)})
            except ModelUnavailable as exc:
                self.respond(503, {"error": str(exc)})
            except DatabaseUnavailable as exc:
                logger.exception("Database request failed")
                self.respond(503, {"error": str(exc)})
            except ValueError:
                self.respond(400, {"error": "Invalid request encoding or Content-Length"})
            except Exception:
                logger.exception("Unexpected request failure")
                self.respond(500, {"error": "Internal service error"})
            finally:
                if active_service is not None and self.path in {"/projects", "/remember", "/updates", "/updates/natural", "/plans", "/plans/revise", "/handoffs", "/handoffs/claim", "/recall", "/history", "/analyze"}:
                    client = self.headers.get("X-Retract-Client", "api")
                    active_service.activity.record(self.path, body if isinstance(body, dict) else {},
                                            self.response_status, client if client in {"mcp", "dashboard"} else "api",
                                            (monotonic() - started) * 1000)

    return Handler


def make_server(service: MemoryService, port: int = 8100, *, hosted=None) -> ThreadingHTTPServer:
    from threading import BoundedSemaphore

    class BoundedServer(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 64

        def __init__(self, *args):
            self.slots = BoundedSemaphore(32)
            super().__init__(*args)

        def process_request(self, request, client_address):
            if not self.slots.acquire(blocking=False):
                try:
                    request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                finally:
                    self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except BaseException:
                self.slots.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.slots.release()

    return BoundedServer(("0.0.0.0" if hosted else "127.0.0.1", port), make_handler(service, hosted))
