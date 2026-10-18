from copy import deepcopy
from dataclasses import asdict
from email.message import Message
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from retract.api import dispatch
from retract.mcp import MAX_FRAME_BYTES, McpServer, VERSIONS, serve
from retract.mcp_tools import ApiError, LocalApi, definitions, route_tool
from retract.models import ValidationError
from tests import test_service
from tests.test_inference import natural_request
from tests.test_policy import confirmed_update


ROOT = Path(__file__).resolve().parents[1]


def request(method, params=None, request_id=1):
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


def initialize(server, version=VERSIONS[0]):
    response = server.handle(request("initialize", {"protocolVersion": version, "capabilities": {},
                                                    "clientInfo": {"name": "test-client", "version": "1"}}))
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return response


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.api = SimpleNamespace(call=Mock(return_value={"active_facts": [], "sources": [], "project_revision": 0}))
        self.server = McpServer(self.api)

    def test_lifecycle_negotiates_supported_or_fallback_version(self):
        for version in (*VERSIONS, "2099-01-01"):
            server = McpServer(self.api)
            result = initialize(server, version)["result"]
            self.assertEqual(result["protocolVersion"], version if version in VERSIONS else VERSIONS[0])
            self.assertEqual(result["capabilities"], {"tools": {"listChanged": False}})
            self.assertEqual(result["serverInfo"]["name"], "retract")

    def test_tools_require_completed_handshake(self):
        self.assertEqual(self.server.handle(request("tools/list"))["error"]["code"], -32002)
        self.assertEqual(self.server.handle(request("ping"))["result"], {})
        self.assertEqual(self.server.handle(request("initialize"))["error"]["code"], -32602)
        initialize(self.server)
        self.assertEqual(self.server.handle(request("initialize"))["error"]["code"], -32600)

    def test_tools_and_hints_match_their_effects(self):
        initialize(self.server)
        tools = self.server.handle(request("tools/list"))["result"]["tools"]
        self.assertEqual({tool["name"] for tool in tools}, {"remember", "process_update", "recall", "history", "record_plan", "revise_plan", "handoff", "claim_handoff"})
        self.assertEqual({tool["name"] for tool in tools if tool["annotations"]["readOnlyHint"]}, {"recall", "history"})
        self.assertTrue(all(tool["inputSchema"]["type"] == "object" for tool in tools))

    def test_successful_call_returns_actual_api_payload(self):
        initialize(self.server)
        result = self.server.handle(request("tools/call", {"name": "recall", "arguments": {
            "project_id": "project", "scope": "web/main"}}))["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"])["project_revision"], 0)
        self.api.call.assert_called_once_with("/recall", {"project_id": "project", "scope": "web/main"})

    def test_notifications_cannot_mutate_memory(self):
        initialize(self.server)
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "tools/call", "params": {
            "name": "remember", "arguments": {}}}))
        self.api.call.assert_not_called()

    def test_protocol_errors_are_distinct_from_tool_errors(self):
        initialize(self.server)
        self.assertEqual(self.server.handle(request("unknown"))["error"]["code"], -32601)
        self.assertEqual(self.server.handle(request("tools/call", {"name": "unknown"}))["error"]["code"], -32602)
        result = self.server.handle(request("tools/call", {"name": "remember", "arguments": {}}))["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"])["status"], 400)

    def test_backend_failure_is_visible_and_never_fabricates_context(self):
        initialize(self.server)
        self.api.call.side_effect = ApiError("Model rate limit", 429, 90)
        result = self.server.handle(request("tools/call", {"name": "recall", "arguments": {
            "project_id": "project", "scope": "web/main"}}))["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"]), {"error": "Model rate limit", "status": 429, "retry_after_seconds": 90})

    def test_invalid_requests_and_ids_are_rejected(self):
        for value in ([], {}, request("ping", request_id=True), request("ping", request_id=None),
                      {"jsonrpc": "1.0", "method": "ping", "id": 1}):
            with self.subTest(value=value):
                self.assertEqual(self.server.handle(value)["error"]["code"], -32600)

    def test_stdio_frames_reject_bad_json_duplicates_and_oversize_then_recover(self):
        frames = [b"not json\n", b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n',
                  b"[" * 1500 + b"]" * 1500 + b"\n",
                  b"x" * (MAX_FRAME_BYTES + 5) + b"\n", json.dumps(request("ping", request_id=7)).encode() + b"\n"]
        output = BytesIO()
        serve("http://127.0.0.1:8100", source=BytesIO(b"".join(frames)), output=output, api=self.api)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        codes = [row.get("error", {}).get("code") for row in responses]
        self.assertEqual(codes[:2], [-32700, -32700])
        # Python versions differ in whether their JSON decoder accepts this
        # nesting depth. Either parsing rejection or invalid-request is correct.
        self.assertIn(codes[2], (-32700, -32600))
        self.assertEqual(codes[3:], [-32600, None])
        self.assertEqual(responses[-1]["id"], 7)

    def test_actual_subprocess_stdio_is_json_only_and_exits_on_eof(self):
        frames = [request("initialize", {"protocolVersion": VERSIONS[0], "capabilities": {},
                                         "clientInfo": {"name": "protocol-probe", "version": "1"}}),
                  {"jsonrpc": "2.0", "method": "notifications/initialized"}, request("tools/list", request_id=2),
                  request("ping", request_id=3)]
        process = subprocess.run([sys.executable, "-m", "retract", "mcp"], cwd=ROOT,
                                 env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "RETRACT_URL": "http://127.0.0.1:8100"},
                                 input="".join(json.dumps(frame) + "\n" for frame in frames), text=True,
                                 capture_output=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([row["id"] for row in responses], [1, 2, 3])
        self.assertEqual(len(responses[1]["result"]["tools"]), 8)
        self.assertEqual(process.stderr, "")

    def test_activity_records_actual_ids_without_source_text(self):
        with tempfile.TemporaryDirectory() as directory:
            logfile = Path(directory) / "activity.jsonl"
            server = McpServer(self.api, logfile)
            initialize(server)
            server.handle(request("tools/call", {"name": "recall", "arguments": {"project_id": "project", "scope": "web/main"}}))
            record = json.loads(logfile.read_text())
            self.assertEqual(record["client"], "test-client")
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["tool"], "recall")
            self.assertNotIn("text", record)
            self.assertNotIn("arguments", record)


class RoutingTests(unittest.TestCase):
    def test_both_update_modes_map_to_existing_api(self):
        natural = {**asdict(natural_request()), "mode": "natural"}
        structured = {**asdict(confirmed_update()), "mode": "structured"}
        self.assertEqual(route_tool("process_update", natural)[0], "/updates/natural")
        self.assertEqual(route_tool("process_update", structured)[0], "/updates")
        with self.assertRaises(ValidationError):
            route_tool("process_update", {**natural, "classification": "confirmed_change"})

    def test_invalid_arguments_never_reach_api(self):
        for name, args in (("recall", {"project_id": "p", "scope": "s", "subjects": "subject"}),
                           ("history", {"project_id": "p", "fact_id": "F1", "event_id": "U1"}),
                           ("history", {"project_id": "p", "fact_id": None}), ("remember", [])):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                route_tool(name, args)

    def test_local_gateway_rejects_remote_hosts_credentials_and_paths(self):
        for value in ("https://127.0.0.1:8100", "http://example.com:8100", "http://user@localhost:8100", "http://localhost:8100/path",
                      "http://localhost:8100?query=1", "http://localhost", "http://localhost:bad"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                LocalApi(value)

    def test_local_gateway_sends_json_and_surfaces_http_error(self):
        seen = []
        def opener(request, timeout):
            seen.append((request.full_url, json.loads(request.data), timeout))
            return BytesIO(b'{"active_facts":[],"project_revision":3}')
        api = LocalApi("http://127.0.0.1:8100", opener)
        self.assertEqual(api.call("/recall", {"project_id": "p", "scope": "s"})["project_revision"], 3)
        self.assertEqual(seen[0][2], 15)
        def failure(*args, **kwargs):
            raise HTTPError("http://localhost:8100/recall", 409, "Conflict", Message(), BytesIO(b'{"error":"Stale revision"}'))
        with self.assertRaises(ApiError) as raised:
            LocalApi("http://localhost:8100", failure).call("/recall", {})
        self.assertEqual(raised.exception.status, 409)

    def test_local_gateway_fails_clearly_on_unavailable_or_invalid_output(self):
        def unavailable(*args, **kwargs):
            raise URLError("internal secret network info")
        with self.assertRaises(ApiError) as raised:
            LocalApi("http://localhost:8100", unavailable).call("/recall", {})
        self.assertNotIn("secret", str(raised.exception))
        for raw in (b"bad", b"[]"):
            with self.subTest(raw=raw), self.assertRaises(ApiError):
                LocalApi.read_json(BytesIO(raw))


class ApplicationBridgeTests(unittest.TestCase):
    def setUp(self):
        test_service.ServiceTests.setUp(self)
        self.api = SimpleNamespace(call=lambda route, body: dispatch(self.service, route, body))
        self.server = McpServer(self.api)
        initialize(self.server)

    def tool(self, name, arguments):
        result = self.server.handle(request("tools/call", {"name": name, "arguments": arguments}))["result"]
        self.assertFalse(result["isError"], result)
        return json.loads(result["content"][0]["text"])

    def test_tool_correction_recall_history_and_proposal_use_shared_policy(self):
        result = self.tool("process_update", {**asdict(confirmed_update()), "mode": "structured"})
        self.assertEqual(result["flagged_plan_ids"], ["P1"])
        recall = self.tool("recall", {"project_id": "account-settings", "scope": "web-client/main"})
        self.assertEqual([fact["id"] for fact in recall["active_facts"]], ["F5"])
        history = self.tool("history", {"project_id": "account-settings", "event_id": "U1"})
        self.assertEqual(history["source"]["id"], "S-U1")

    def test_tool_validation_preserves_memory(self):
        before = deepcopy(self.store.__dict__)
        result = self.server.handle(request("tools/call", {"name": "remember", "arguments": {}}))["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(self.store.__dict__, before)
