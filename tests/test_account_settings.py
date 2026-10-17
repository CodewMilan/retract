from html.parser import HTMLParser
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retract.demo import DemoApp, make_demo_handler
from tests.test_demo import ProfileFixture
from tests.test_http import RequestSocket


class PageStructure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = {}
        self.labels = []
        self.external = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                raise AssertionError('Duplicate element ID')
            self.ids[attrs['id']] = (tag, attrs)
        if tag == 'label' and 'for' in attrs:
            self.labels.append(attrs['for'])
        if tag in ('script', 'link'):
            self.external.append(attrs.get('src', attrs.get('href', '')))


class AccountSettingsTests(unittest.TestCase):
    def setUp(self):
        self.app = DemoApp(ProfileFixture())

    def request(self, path='/settings', headers=None, method='GET'):
        supplied = {'Host': '127.0.0.1:8101', **(headers or {})}
        raw = '\r\n'.join([f'{method} {path} HTTP/1.1', *(f'{key}: {value}' for key, value in supplied.items()), '', ''])
        sock = RequestSocket(raw.encode())
        make_demo_handler(self.app)(sock, ('127.0.0.1', 1000), SimpleNamespace(server_port=8101))
        head, body = bytes(sock.output).split(b'\r\n\r\n', 1)
        return int(head.split(b' ')[1]), head.decode(), body

    def test_page_and_packaged_assets_load_without_a_session(self):
        for path, mime in [('/settings', 'text/html'), ('/assets/account/settings.css', 'text/css'),
                           ('/assets/account/settings.mjs', 'text/javascript'), ('/assets/account/account-client.mjs', 'text/javascript')]:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn(mime, headers)
                self.assertIn("script-src 'self'", headers)
                self.assertIn("frame-ancestors 'none'", headers)
                self.assertIn('Cache-Control: no-store', headers)
                self.assertIn('X-Content-Type-Options: nosniff', headers)
                self.assertNotIn('Set-Cookie:', headers)
                self.assertGreater(len(body), 100)
        self.assertEqual(self.app.sessions, {})

    def test_markup_has_labels_initial_loading_state_and_readonly_email(self):
        page = PageStructure()
        page.feed(self.request()[2].decode())
        self.assertTrue(set(page.labels) <= page.ids.keys())
        self.assertIn('hidden', page.ids['profile'][1])
        self.assertIn('hidden', page.ids['signed-out'][1])
        self.assertEqual(page.ids['loading'][1]['aria-busy'], 'true')
        self.assertIn('readonly', page.ids['email'][1])
        self.assertIn('required', page.ids['display-name'][1])
        self.assertEqual(page.ids['display-name'][1]['autocomplete'], 'name')
        self.assertEqual(set(page.external), {'/assets/account/settings.css', '/assets/account/settings.mjs'})

    def test_page_keeps_strict_local_origin_checks(self):
        for headers in ({'Host': 'external.test'}, {'Origin': 'https://external.test'}, {'Origin': 'http://['}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(headers=headers)[0], 403)

    def test_asset_routes_cannot_read_arbitrary_files(self):
        for path in ('/assets/account/../../.env', '/assets/account/%2e%2e/demo.py', '/src/retract/demo.py', '/settings?file=.env'):
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertNotEqual(status, 200)
                self.assertIn('error', json.loads(body))

    def test_shell_is_available_if_storage_fails_after_service_start(self):
        with patch.object(self.app.profiles, 'get', side_effect=OSError('private storage diagnostics')):
            self.assertEqual(self.request()[0], 200)
            status, _, body = self.request('/api/session')
            self.assertEqual(status, 401)
            self.assertNotIn(b'private', body)
