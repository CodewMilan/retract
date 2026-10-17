"""Small local JSON adapter. Run one process; all writes share MemoryService.lock."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from urllib.parse import urlsplit

from .graph import DatabaseUnavailable
from .models import (
    ConflictError, NotFoundError, PlanInput, RememberInput, UpdateInput,
    ValidationError, parse,
)
from .service import MemoryService


MAX_BODY = 65536
logger = logging.getLogger(__name__)


def dispatch(service: MemoryService, path: str, body: dict) -> dict:
    if path == "/projects":
        if set(body) != {"project_id", "name"}:
            raise ValidationError("Supply project_id and name")
        return service.create_project(**body)
    if path == "/remember":
        return service.remember(parse(RememberInput, body))
    if path == "/updates":
        return service.process_update(parse(UpdateInput, body))
    if path == "/plans":
        return service.record_plan(parse(PlanInput, body))
    if path == "/recall":
        if not {"project_id", "scope"} <= body.keys() or set(body) - {"project_id", "scope", "subjects"}:
            raise ValidationError("Supply project_id, scope, and optional subjects")
        return service.recall(**body)
    if path == "/history":
        if "project_id" not in body or set(body) - {"project_id", "fact_id", "event_id"}:
            raise ValidationError("Supply project_id and either fact_id or event_id")
        return service.history(**body)
    raise NotFoundError("Unknown API route")


def make_handler(service: MemoryService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RETRACT/0.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            # Source text and request bodies are deliberately absent from logs.
            logger.info(format, *args)

        def respond(self, status: int, result: dict):
            encoded = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(encoded)
            self.close_connection = True

        def valid_origin(self):
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            origin = self.headers.get("Origin")
            try:
                return self.headers.get("Host") in allowed and (
                    origin is None or (urlsplit(origin).scheme == "http" and urlsplit(origin).netloc in allowed)
                )
            except ValueError:
                return False

        def do_GET(self):
            if not self.valid_origin():
                self.respond(403, {"error": "Local origin required"})
                return
            if self.path != "/health":
                self.respond(404, {"error": "Unknown API route"})
                return
            try:
                with service.lock:
                    service.store.query("RETURN 1", {})
                self.respond(200, {"status": "ok", "storage": "falkordb"})
            except DatabaseUnavailable as exc:
                self.respond(503, {"error": str(exc)})

        def do_POST(self):
            try:
                if not self.valid_origin():
                    self.respond(403, {"error": "Local origin required"})
                    return
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
                self.respond(200, dispatch(service, self.path, body))
            except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                self.respond(400, {"error": str(exc)})
            except ConflictError as exc:
                self.respond(409, {"error": str(exc)})
            except NotFoundError as exc:
                self.respond(404, {"error": str(exc)})
            except DatabaseUnavailable as exc:
                logger.exception("Database request failed")
                self.respond(503, {"error": str(exc)})
            except ValueError:
                self.respond(400, {"error": "Invalid request encoding or Content-Length"})
            except Exception:
                logger.exception("Unexpected request failure")
                self.respond(500, {"error": "Internal service error"})

    return Handler


def make_server(service: MemoryService, port: int = 8100) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(service))
