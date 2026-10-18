"""Synthetic account API for the coding-client exercise, not an auth product.

The shipped runtime profile store is PostgreSQL. Tests inject a test-only store.
The explicit demo login selects Alice or Bob without a password, so the fixture
is bound to localhost and must never be used for real accounts.
"""

from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from importlib.resources import files
import os
import re
import secrets
import sys
from threading import RLock
import time
from urllib.parse import urlsplit


COOKIE = "retract_demo_session"


class DemoError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class PostgresProfiles:
    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row
        self.connect = lambda: psycopg.connect(url, connect_timeout=3, row_factory=dict_row)

    def health(self):
        with self.connect() as db:
            db.execute("SELECT 1").fetchone()

    def seed(self):
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS retract_demo_profiles "
                       "(id TEXT PRIMARY KEY, display_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE)")
            for values in (("alice", "Alice Example", "alice@example.test"), ("bob", "Bob Example", "bob@example.test")):
                db.execute("INSERT INTO retract_demo_profiles (id, display_name, email) VALUES (%s, %s, %s) "
                           "ON CONFLICT (id) DO NOTHING", values)

    def get(self, user_id):
        with self.connect() as db:
            return db.execute("SELECT id, display_name, email FROM retract_demo_profiles WHERE id = %s", (user_id,)).fetchone()

    def update(self, user_id, display_name):
        with self.connect() as db:
            return db.execute("UPDATE retract_demo_profiles SET display_name = %s WHERE id = %s "
                              "RETURNING id, display_name, email", (display_name, user_id)).fetchone()


class DemoApp:
    def __init__(self, profiles, *, clock=time.monotonic):
        self.profiles = profiles
        self.clock = clock
        self.sessions = {}
        self.lock = RLock()

    def session(self, headers):
        if headers.get("Authorization"):
            raise DemoError(401, "Browser authentication requires the HTTP-only session cookie")
        cookies = SimpleCookie()
        try:
            cookies.load(headers.get("Cookie", ""))
        except CookieError:
            raise DemoError(401, "Sign in to the demo") from None
        token = cookies[COOKIE].value if COOKIE in cookies else None
        session = self.sessions.get(token)
        if session is None or session["expires"] <= self.clock():
            self.sessions.pop(token, None)
            raise DemoError(401, "Sign in to the demo")
        return token, session

    def dispatch(self, method, path, headers, body):
        with self.lock:
            if method == "GET" and path == "/health":
                self.profiles.health()
                return {"status": "ok", "storage": "postgresql"}, None
            if method == "POST" and path == "/demo/login":
                if set(body) != {"user_id"} or body["user_id"] not in ("alice", "bob"):
                    raise DemoError(400, "Choose synthetic user alice or bob")
                profile = self.profiles.get(body["user_id"])
                if profile is None:
                    raise DemoError(404, "Demo profile missing; run the explicit seed command")
                # Expired fixture sessions must not accumulate indefinitely.
                self.sessions = {token: value for token, value in self.sessions.items() if value["expires"] > self.clock()}
                if len(self.sessions) >= 128:
                    raise DemoError(429, "Too many demo sessions; sign out or restart the fixture")
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                self.sessions[token] = {"user_id": profile["id"], "csrf": csrf, "expires": self.clock() + 3600}
                return {"user": profile, "csrf_token": csrf}, f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600"
            token, session = self.session(headers)
            if method == "GET" and path == "/api/session":
                return {"user": self.profiles.get(session["user_id"]), "csrf_token": session["csrf"]}, None
            if method in ("POST", "PATCH"):
                supplied = headers.get("X-CSRF-Token", "")
                if not isinstance(supplied, str) or not supplied.isascii() or not secrets.compare_digest(supplied, session["csrf"]):
                    raise DemoError(403, "Valid X-CSRF-Token required")
            if method == "POST" and path == "/demo/logout":
                self.sessions.pop(token)
                return {"signed_out": True}, f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
            if method in ("GET", "PATCH") and path.startswith("/api/profiles/"):
                profile_id = path.removeprefix("/api/profiles/")
                if profile_id != session["user_id"]:
                    raise DemoError(403, "Users may access only their own profile")
                if method == "GET":
                    return {"user": self.profiles.get(profile_id)}, None
                if set(body) != {"display_name"} or not isinstance(body["display_name"], str) or not 1 <= len(body["display_name"].strip()) <= 80:
                    raise DemoError(400, "Supply a display_name with 1–80 characters")
                return {"user": self.profiles.update(profile_id, body["display_name"].strip())}, None
            raise DemoError(404, "Unknown demo route")


def make_demo_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass

        def respond(self, status, result, cookie=None):
            encoded = json.dumps(result).encode()
            self.send_response(status)
            for name, value in (("Content-Type", "application/json"), ("Content-Length", str(len(encoded))),
                                ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), ("Connection", "close")):
                self.send_header(name, value)
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(encoded)
            self.close_connection = True

        def handle_route(self):
            try:
                allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
                origin = self.headers.get("Origin")
                try:
                    valid = self.headers.get("Host") in allowed and (origin is None or (urlsplit(origin).scheme == "http" and urlsplit(origin).netloc in allowed))
                except ValueError:
                    valid = False
                if not valid:
                    raise DemoError(403, "Local demo origin required")
                assets = {"/settings": ("index.html", "text/html"),
                          "/assets/account/settings.css": ("settings.css", "text/css"),
                          "/assets/account/settings.mjs": ("settings.mjs", "text/javascript"),
                          "/assets/account/account-client.mjs": ("account-client.mjs", "text/javascript")}
                if self.command == "GET" and self.path.startswith("/assets/account/fonts/"):
                    name = self.path.removeprefix("/assets/account/fonts/")
                    font = files("retract").joinpath("web", "fonts", name)
                    if not (re.fullmatch(r"[a-z0-9-]+\.woff2", name) and font.is_file()):
                        raise DemoError(404, "Unknown demo route")
                    encoded = font.read_bytes()
                    self.send_response(200)
                    for header, value in (("Content-Type", "font/woff2"), ("Content-Length", str(len(encoded))),
                                          ("Cache-Control", "public, max-age=86400"), ("X-Content-Type-Options", "nosniff"),
                                          ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
                                          ("Connection", "close")):
                        self.send_header(header, value)
                    self.end_headers()
                    self.wfile.write(encoded)
                    self.close_connection = True
                    return
                if self.command == "GET" and self.path in assets:
                    name, mime = assets[self.path]
                    encoded = files("retract").joinpath("account_web", name).read_bytes()
                    self.send_response(200)
                    for name, value in (("Content-Type", mime + "; charset=utf-8"), ("Content-Length", str(len(encoded))),
                                        ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                                        ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
                                        ("Connection", "close")):
                        self.send_header(name, value)
                    self.end_headers()
                    self.wfile.write(encoded)
                    self.close_connection = True
                    return
                body = {}
                if self.command in ("POST", "PATCH"):
                    if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                        raise DemoError(415, "Content-Type must be application/json")
                    if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                        raise DemoError(400, "Supply one Content-Length header")
                    length = int(self.headers["Content-Length"])
                    if not 0 < length <= 4096:
                        raise DemoError(413, "Demo request body limit is 4096 bytes")
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise DemoError(400, "Incomplete request body")
                    body = json.loads(raw)
                    if not isinstance(body, dict):
                        raise DemoError(400, "Request body must be a JSON object")
                result, cookie = app.dispatch(self.command, self.path, self.headers, body)
                self.respond(200, result, cookie)
            except DemoError as exc:
                self.respond(exc.status, {"error": str(exc)})
            except (ValueError, UnicodeError):
                self.respond(400, {"error": "Invalid request body or length"})
            except Exception:
                self.respond(503, {"error": "Demo storage unavailable; check PostgreSQL and seed the fixture"})

        do_GET = handle_route
        do_POST = handle_route
        do_PATCH = handle_route
    return Handler


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Synthetic account API for the RETRACT coding exercise")
    parser.add_argument("--seed", action="store_true", help="Explicitly create and seed synthetic PostgreSQL profiles, then exit")
    parser.add_argument("--port", type=int, default=8101)
    args = parser.parse_args()
    try:
        store = PostgresProfiles(os.getenv("DEMO_DATABASE_URL", "postgresql://retract_demo:local_demo_only@127.0.0.1:54330/retract_demo"))
        if args.seed:
            store.seed()
            print("Synthetic demo profiles seeded; existing profiles retained")
            return
        store.health()
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_demo_handler(DemoApp(store)))
        print(f"Synthetic account settings on http://127.0.0.1:{server.server_port}/settings", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    except KeyboardInterrupt:
        pass
    except Exception:
        print("Demo unavailable: install .[demo], start PostgreSQL, and run python -m retract.demo --seed", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
