from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retract.api import make_handler
from retract.graph import DatabaseUnavailable
from retract.service import MemoryService
from tests.support import ModelStore


class RequestSocket:
    """In-process transport: exercise the HTTP handler without binding a port."""

    def __init__(self, raw):
        self.input = BytesIO(raw)
        self.output = bytearray()

    def makefile(self, *args):
        return self.input

    def settimeout(self, timeout):
        pass

    def sendall(self, data):
        self.output.extend(data)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.store = ModelStore()
        self.service = MemoryService(self.store)
        self.service.create_project("project", "Project")

    def request(self, route="/recall", body=None, *, headers=None, raw_body=None, method="POST"):
        encoded = json.dumps(body or {"project_id": "project", "scope": "web/main"}).encode() if raw_body is None else raw_body
        values = {"Host": "127.0.0.1:8100", "Content-Type": "application/json", "Content-Length": str(len(encoded))}
        values.update(headers or {})
        head = "\r\n".join([f"{method} {route} HTTP/1.1", *(f"{key}: {value}" for key, value in values.items()), "", ""])
        connection = RequestSocket(head.encode() + encoded)
        make_handler(self.service)(connection, ("127.0.0.1", 1234), SimpleNamespace(server_port=8100))
        raw_head, raw_result = bytes(connection.output).split(b"\r\n\r\n", 1)
        status = int(raw_head.split(b" ", 2)[1])
        return status, json.loads(raw_result), raw_head.decode()

    def test_recall_serves_actual_application_result(self):
        status, result, headers = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(result["active_facts"], [])
        self.assertEqual(result["project_revision"], 0)
        self.assertIn("Cache-Control: no-store", headers)

    def test_source_validation_returns_400(self):
        status, _, _ = self.request("/remember", {"source": {"id": "missing-fields"}})
        self.assertEqual(status, 400)

    def test_unknown_project_and_route_return_404(self):
        self.assertEqual(self.request(body={"project_id": "unknown", "scope": "web/main"})[0], 404)
        self.assertEqual(self.request("/unknown")[0], 404)

    def test_external_or_malformed_origin_and_host_are_rejected(self):
        for headers in ({"Origin": "https://example.com"}, {"Origin": "http://["}, {"Host": "example.com:8100"}):
            for method in ("GET", "POST"):
                with self.subTest(headers=headers, method=method):
                    self.assertEqual(self.request("/health", headers=headers, method=method)[0], 403)

    def test_json_content_type_is_required(self):
        self.assertEqual(self.request(headers={"Content-Type": "text/plain"})[0], 415)

    def test_oversized_body_is_rejected_before_reading(self):
        self.assertEqual(self.request(headers={"Content-Length": "65537"})[0], 413)

    def test_malformed_body_and_length_are_rejected(self):
        for body in (b"not json", b"[]", b"\xff"):
            with self.subTest(body=body):
                self.assertEqual(self.request(raw_body=body)[0], 400)
        self.assertEqual(self.request(headers={"Content-Length": "wrong"})[0], 400)
        self.assertEqual(self.request(headers={"Transfer-Encoding": "chunked"})[0], 400)
        self.assertEqual(self.request(headers={"Content-Length": "100000000000000000000000000000"})[0], 413)

    def test_duplicate_length_and_truncated_body_are_rejected(self):
        self.assertEqual(self.request(headers={"Content-Length": "2\r\nContent-Length: 2"}, raw_body=b"{}")[0], 400)
        self.assertEqual(self.request(headers={"Content-Length": "10"}, raw_body=b"{}")[0], 400)

    def test_unavailable_database_fails_clearly_without_returning_context(self):
        with patch.object(self.store, "get", side_effect=DatabaseUnavailable("Storage unavailable")):
            with self.assertLogs("retract.api", level="ERROR"):
                status, result, _ = self.request()
        self.assertEqual(status, 503)
        self.assertEqual(result, {"error": "Storage unavailable"})

    def test_untrusted_remember_returns_conflict_without_mutating_memory(self):
        body = {"project_id": "project", "scope": "web/main", "subject": "auth", "predicate": "method", "value": "cookies",
                "source": {"id": "source", "kind": "document", "title": "Untrusted", "content": "Some note"}}
        self.assertEqual(self.request("/remember", body)[0], 409)
        self.assertEqual(self.service.project("project")["revision"], 0)
