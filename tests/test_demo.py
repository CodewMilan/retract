from copy import deepcopy
import json
from types import SimpleNamespace
import unittest

from retract.demo import COOKIE, DemoApp, DemoError, make_demo_handler
from tests.test_http import RequestSocket


class ProfileFixture:
    """Test-only profile store. Runtime demo uses PostgreSQL, never this model."""

    def __init__(self):
        self.profiles = {"alice": {"id": "alice", "display_name": "Alice Example", "email": "alice@example.test"},
                         "bob": {"id": "bob", "display_name": "Bob Example", "email": "bob@example.test"}}

    def health(self):
        pass

    def get(self, user_id):
        return deepcopy(self.profiles.get(user_id))

    def update(self, user_id, display_name):
        self.profiles[user_id]["display_name"] = display_name
        return self.get(user_id)


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.profiles = ProfileFixture()
        self.now = 100
        self.app = DemoApp(self.profiles, clock=lambda: self.now)

    def login(self, user="alice"):
        result, cookie = self.app.dispatch("POST", "/demo/login", {}, {"user_id": user})
        return result, {"Cookie": cookie.split(";", 1)[0], "X-CSRF-Token": result["csrf_token"]}, cookie

    def http(self, method, path, body=None, headers=None):
        encoded = json.dumps(body or {}).encode()
        values = {"Host": "127.0.0.1:8101", "Content-Type": "application/json", "Content-Length": str(len(encoded)), **(headers or {})}
        raw = "\r\n".join([f"{method} {path} HTTP/1.1", *(f"{key}: {value}" for key, value in values.items()), "", ""]).encode() + encoded
        sock = RequestSocket(raw)
        make_demo_handler(self.app)(sock, ("127.0.0.1", 1000), SimpleNamespace(server_port=8101))
        head, result = bytes(sock.output).split(b"\r\n\r\n", 1)
        return int(head.split(b" ", 2)[1]), json.loads(result), head.decode()

    def test_synthetic_login_sets_http_only_strict_cookie_and_csrf(self):
        result, headers, cookie = self.login()
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertTrue(headers["Cookie"].startswith(COOKIE + "="))
        self.assertEqual(result["user"]["id"], "alice")
        self.assertGreater(len(result["csrf_token"]), 20)

    def test_profile_update_requires_cookie_and_preserves_other_user(self):
        _, headers, _ = self.login()
        before = self.profiles.get("bob")
        result, _ = self.app.dispatch("PATCH", "/api/profiles/alice", headers, {"display_name": "Alice Updated"})
        self.assertEqual(result["user"]["display_name"], "Alice Updated")
        self.assertEqual(self.profiles.get("bob"), before)

    def test_ownership_is_enforced_for_reads_and_writes(self):
        _, headers, _ = self.login()
        for method in ("GET", "PATCH"):
            with self.subTest(method=method), self.assertRaises(DemoError) as raised:
                self.app.dispatch(method, "/api/profiles/bob", headers, {"display_name": "Wrong"})
            self.assertEqual(raised.exception.status, 403)
        self.assertEqual(self.profiles.get("bob")["display_name"], "Bob Example")

    def test_missing_cookie_and_legacy_bearer_requests_are_rejected(self):
        _, headers, _ = self.login()
        for supplied in ({}, {"Authorization": "Bearer obsolete"}, {**headers, "Authorization": "Bearer obsolete"}):
            with self.subTest(headers=supplied), self.assertRaises(DemoError) as raised:
                self.app.dispatch("GET", "/api/session", supplied, {})
            self.assertEqual(raised.exception.status, 401)

    def test_write_requires_valid_csrf_token(self):
        _, headers, _ = self.login()
        for token in ("", "wrong", "é"):
            with self.subTest(token=token), self.assertRaises(DemoError) as raised:
                self.app.dispatch("PATCH", "/api/profiles/alice", {**headers, "X-CSRF-Token": token}, {"display_name": "Wrong"})
            self.assertEqual(raised.exception.status, 403)
        self.assertEqual(self.profiles.get("alice")["display_name"], "Alice Example")

    def test_expired_session_and_logout_stop_access(self):
        _, headers, _ = self.login()
        self.app.dispatch("POST", "/demo/logout", headers, {})
        with self.assertRaises(DemoError):
            self.app.dispatch("GET", "/api/session", headers, {})
        _, headers, _ = self.login()
        self.now += 3601
        with self.assertRaises(DemoError):
            self.app.dispatch("GET", "/api/session", headers, {})

    def test_only_display_name_is_mutable_and_validated(self):
        _, headers, _ = self.login()
        for body in ({"id": "bob"}, {"email": "changed@example.test"}, {"display_name": " "}, {"display_name": "x" * 81}):
            with self.subTest(body=body), self.assertRaises(DemoError) as raised:
                self.app.dispatch("PATCH", "/api/profiles/alice", headers, body)
            self.assertEqual(raised.exception.status, 400)

    def test_http_origin_and_json_contract_are_enforced(self):
        for origin in ("https://example.com", "http://["):
            self.assertEqual(self.http("POST", "/demo/login", {"user_id": "alice"}, {"Origin": origin})[0], 403)
        self.assertEqual(self.http("POST", "/demo/login", {"user_id": "alice"}, {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.http("POST", "/demo/login", {"user_id": "unknown"})[0], 400)

    def test_http_cookie_session_and_update_round_trip(self):
        status, result, raw_headers = self.http("POST", "/demo/login", {"user_id": "alice"})
        self.assertEqual(status, 200)
        cookie = next(line.split(": ", 1)[1] for line in raw_headers.splitlines() if line.startswith("Set-Cookie:"))
        headers = {"Cookie": cookie.split(";", 1)[0], "X-CSRF-Token": result["csrf_token"]}
        status, session, _ = self.http("GET", "/api/session", headers=headers)
        self.assertEqual(session["user"]["id"], "alice")
        status, updated, _ = self.http("PATCH", "/api/profiles/alice", {"display_name": "Alice Updated"}, headers)
        self.assertEqual(status, 200)
        self.assertEqual(updated["user"]["display_name"], "Alice Updated")

    def test_store_failure_does_not_report_a_successful_update(self):
        def unavailable(*args):
            raise RuntimeError("private database credentials")
        self.app.profiles.get = unavailable
        status, result, _ = self.http("POST", "/demo/login", {"user_id": "alice"})
        self.assertEqual(status, 503)
        self.assertNotIn("private", str(result))
