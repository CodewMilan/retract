"""/ is the marketing page in every mode. The workspace sign-in stays on /dashboard."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retract.api import make_handler
from tests.test_http import RequestSocket


class Config:
    origin = "https://retract.up.railway.app"

    def csp(self):
        return "default-src 'self'; script-src 'self'"


def request(handler, path, host):
    raw = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode()
    sock = RequestSocket(raw)
    handler(sock, ("127.0.0.1", 1), SimpleNamespace(server_port=8100))
    header, body = bytes(sock.output).split(b"\r\n\r\n", 1)
    return int(header.split(b" ")[1]), header.decode(), body


class LandingRouteTests(unittest.TestCase):
    def setUp(self):
        self.hosted = make_handler(None, SimpleNamespace(config=Config()))
        self.local = make_handler(None)

    def test_local_root_is_the_landing_page_and_dashboard_opens_sign_in(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<!doctype html><title>Landing marker</title>")
            (root / "assets").mkdir()
            (root / "assets" / "app-Ab12.js").write_text("landing-script")
            with patch("retract.landing_pages.landing_root", return_value=root):
                status, headers, body = request(self.local, "/", "127.0.0.1:8100")
                script = request(self.local, "/assets/app-Ab12.js", "127.0.0.1:8100")
        self.assertEqual(status, 200)
        self.assertIn("Landing marker", body.decode())
        self.assertNotIn("Sign in.", body.decode())
        self.assertIn("fonts.googleapis.com", headers)
        self.assertEqual(script[2], b"landing-script")
        self.assertIn("Welcome to Retract", request(self.local, "/dashboard", "127.0.0.1:8100")[2].decode())

    def test_hosted_root_is_the_landing_page_and_dashboard_opens_sign_in(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<!doctype html><title>Landing marker</title>")
            (root / "assets").mkdir()
            (root / "assets" / "app-Ab12.js").write_text("landing-script")
            (root / "assets" / "dashboard.mjs").write_text("landing-must-not-win")
            (root / "fonts").mkdir()
            (root / "fonts" / "general-sans-500.woff2").write_bytes(b"woff")
            (root / "secret.txt").write_text("secret")
            with patch("retract.landing_pages.landing_root", return_value=root):
                status, headers, body = request(self.hosted, "/", "retract.up.railway.app")
                script = request(self.hosted, "/assets/app-Ab12.js", "retract.up.railway.app")
                font = request(self.hosted, "/fonts/general-sans-500.woff2", "retract.up.railway.app")
                workspace = request(self.hosted, "/dashboard", "retract.up.railway.app")
                reserved = request(self.hosted, "/assets/dashboard.mjs", "retract.up.railway.app")
                escaped = request(self.hosted, "/assets/../secret.txt", "retract.up.railway.app")
        self.assertEqual(status, 200)
        self.assertIn("Landing marker", body.decode())
        self.assertNotIn("Sign in.", body.decode())
        self.assertIn("fonts.googleapis.com", headers)
        self.assertIn("no-store", headers)
        self.assertEqual(script[2], b"landing-script")
        self.assertIn("public, max-age=86400", script[1])
        self.assertEqual(font[0], 200)
        self.assertIn("font/woff2", font[1])
        self.assertIn("Welcome to Retract", workspace[2].decode())
        self.assertIn("initAuth", reserved[2].decode())
        self.assertNotIn(b"landing-must-not-win", reserved[2])
        self.assertEqual(escaped[0], 404)
        self.assertEqual(request(self.hosted, "/secret.txt", "retract.up.railway.app")[0], 404)

    def test_missing_landing_build_keeps_the_workspace_on_dashboard(self):
        with patch("retract.landing_pages.landing_root", return_value=None):
            status, _, body = request(self.hosted, "/", "retract.up.railway.app")
            local = request(self.local, "/", "127.0.0.1:8100")
            workspace = request(self.local, "/dashboard", "127.0.0.1:8100")
        self.assertEqual(status, 404)
        self.assertIn(b"/dashboard", body)
        self.assertNotIn(b"Sign in.", body)
        self.assertEqual(local[0], 404)
        self.assertIn("Welcome to Retract", workspace[2].decode())
