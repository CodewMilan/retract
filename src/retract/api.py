"""Small local JSON adapter. Run one process; all writes share MemoryService.lock."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from importlib.resources import files
from time import monotonic
from urllib.parse import urlsplit

from .graph import DatabaseUnavailable
from .hosted import AccessError
from .inference import ModelRateLimited, ModelResponseError, ModelUnavailable
from .models import (
    ConflictError, NaturalUpdateInput, NotFoundError, PlanInput, PlanRevisionInput, RememberInput, UpdateInput,
    ValidationError, parse,
)
from .service import MemoryService


MAX_BODY = 65536
logger = logging.getLogger(__name__)


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
    if path == "/recall":
        if not {"project_id", "scope"} <= body.keys() or set(body) - {"project_id", "scope", "subjects"}:
            raise ValidationError("Supply project_id, scope, and optional subjects")
        return service.recall(**body)
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

        def valid_origin(self):
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            origin = self.headers.get("Origin")
            if len(self.headers.get_all("Host", [])) != 1 or len(self.headers.get_all("Origin", [])) > 1:
                return False
            if hosted:
                public_host = urlsplit(hosted.config.origin).netloc
                if self.path == "/health" and self.headers.get("Host") in allowed and origin is None:
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
                if self.path == "/api/config":
                    self.respond(200, hosted.config.public() if hosted else {"mode": "local"})
                    return
                assets = {"/": ("index.html", "text/html"),
                          "/assets/dashboard.css": ("dashboard.css", "text/css"),
                          "/assets/dashboard.mjs": ("dashboard.mjs", "text/javascript"),
                          "/assets/dashboard-model.mjs": ("dashboard-model.mjs", "text/javascript"),
                          "/assets/auth.mjs": ("auth.mjs", "text/javascript")}
                if self.path in assets:
                    name, mime = assets[self.path]
                    encoded = files("retract").joinpath("web", name).read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", mime + "; charset=utf-8")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Content-Security-Policy", hosted.config.csp() if hosted else "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(encoded)
                    self.close_connection = True
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
                if active_service is not None and self.path in {"/projects", "/remember", "/updates", "/updates/natural", "/plans", "/plans/revise", "/recall", "/history"}:
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
