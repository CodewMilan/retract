"""Test-only JSONL-to-HTTP bridge; no socket binding or runtime fake-store mode.

Node client and real-browser tests send requests through the actual demo HTTP
handler. Only the profile storage is a controlled test fixture. Browser-origin
translation is restricted to the explicit intercepted test origin.
"""
import base64
from http.client import HTTPResponse
from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from retract.demo import DemoApp, make_demo_handler
from tests.test_demo import ProfileFixture
from tests.test_http import RequestSocket


class ResponseSocket:
    def __init__(self, raw):
        self.raw = raw

    def makefile(self, *args):
        return BytesIO(self.raw)


class FixtureTransport:
    def __init__(self):
        self.reset()

    def reset(self):
        self.now = 100
        self.profiles = ProfileFixture()
        self.app = DemoApp(self.profiles, clock=lambda: self.now)
        self.fail_next_save = False
        original = self.profiles.update

        def update(*args):
            if self.fail_next_save:
                self.fail_next_save = False
                raise OSError('Injected storage failure')
            return original(*args)
        self.profiles.update = update

    def handle(self, request):
        control = request.get('control')
        if control:
            if control == 'reset':
                self.reset()
            elif control == 'fail_save':
                self.fail_next_save = True
            elif control == 'expire':
                self.now += 3601
            else:
                raise ValueError('Unknown test control')
            return {'ok': True}
        body = request.get('body', '').encode('utf-8')
        method, path = request['method'], request['path']
        if method not in ('GET', 'POST', 'PATCH') or not path.startswith('/') or any(c in path for c in '\r\n '):
            raise ValueError('Invalid test request')
        headers = {'Host': '127.0.0.1:8101', 'Content-Length': str(len(body))}
        for key, value in request.get('headers', {}).items():
            if key.lower() in ('host', 'content-length', 'connection'):
                continue
            if not isinstance(value, str) or any(c in key + value for c in '\r\n'):
                raise ValueError('Invalid test header')
            if key.lower() == 'origin' and value == 'https://account.retract.test':
                value = 'http://127.0.0.1:8101'
            headers[key] = value
        head = '\r\n'.join([f'{method} {path} HTTP/1.1', *(f'{key}: {value}' for key, value in headers.items()), '', '']).encode()
        connection = RequestSocket(head + body)
        make_demo_handler(self.app)(connection, ('127.0.0.1', 1000), SimpleNamespace(server_port=8101))
        response = HTTPResponse(ResponseSocket(bytes(connection.output)))
        response.begin()
        return {'status': response.status, 'headers': dict(response.getheaders()),
                'body_base64': base64.b64encode(response.read()).decode()}


def main():
    fixture = FixtureTransport()
    for line in sys.stdin:
        try:
            result = fixture.handle(json.loads(line))
        except Exception as exc:
            result = {'bridge_error': type(exc).__name__}
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
