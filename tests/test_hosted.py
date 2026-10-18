import base64
from email.message import Message
import json
import os
from types import SimpleNamespace
import time
import unittest
from uuid import uuid4

try:
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    jwt = rsa = None

from retract.api import make_handler
from retract.graph import GraphStore
from retract.hosted import AccessError, ClerkVerifier, HostedConfig, HostedWorkspaces
from retract.service import MemoryService
from tests.test_http import RequestSocket


def config(prefix='test_hosted'):
    return HostedConfig('https://app.example.test', 'https://clerk.example.test',
        'pk_test_' + base64.b64encode(b'clerk.example.test$').decode().rstrip('='), prefix)


@unittest.skipUnless(jwt and rsa, 'Install .[hosted] for authentication tests')
class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.config = config()
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.verifier = ClerkVerifier(self.config)
        self.verifier.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=self.key.public_key()))

    def token(self, user='user_alice', **changes):
        return jwt.encode({'iss': self.config.issuer, 'sub': user, 'sid': 'sess_test',
            'azp': self.config.origin, 'iat': int(time.time()), 'nbf': int(time.time()) - 1,
            'exp': int(time.time()) + 60, **changes}, self.key, algorithm='RS256')

    def test_verified_identity_and_rejected_claims(self):
        self.assertEqual(self.verifier.verify(self.token()), 'user_alice')
        for changes in ({'iss': 'https://attacker.test'}, {'azp': 'https://attacker.test'},
                        {'exp': int(time.time()) - 60}, {'nbf': int(time.time()) + 60},
                        {'sub': ''}, {'sid': ''}, {'sts': 'pending'}):
            with self.subTest(changes=changes), self.assertRaises(AccessError):
                self.verifier.verify(self.token(**changes))
        for bad in ('not-a-jwt', jwt.encode({'sub': 'user_alice'}, 'untrusted-' * 8, algorithm='HS256')):
            with self.assertRaises(AccessError):
                self.verifier.verify(bad)

    def test_hosted_config_fails_closed(self):
        for origin in ('http://app.example.test', 'https://app.example.test/', 'https://user@app.example.test', 'https://app.example.test/path'):
            with self.assertRaises(ValueError):
                HostedConfig(origin, self.config.issuer, self.config.publishable_key)
        with self.assertRaises(ValueError):
            HostedConfig(self.config.origin, self.config.issuer, 'pk_test_wrong')


@unittest.skipUnless(os.getenv('RUN_FALKORDB_TESTS') == '1', 'Requires real FalkorDB')
class HostedGraphTests(IdentityTests):
    def setUp(self):
        super().setUp()
        self.root = GraphStore()
        self.addCleanup(self.root.close)
        self.config = config('test_' + uuid4().hex[:20])
        self.hosted = HostedWorkspaces(self.config, self.root, self.verifier)
        self.addCleanup(self.cleanup_graphs)
        self.handler = make_handler(MemoryService(self.root), self.hosted)

    def cleanup_graphs(self):
        for service in self.hosted.services.values():
            service.store.graph.delete()
        self.hosted.auth.graph.delete()

    def request(self, path, body=None, token=None, method='POST', extra=None):
        encoded = json.dumps(body or {}).encode()
        headers = {'Host': 'app.example.test', 'Origin': self.config.origin,
                   'Content-Type': 'application/json', 'Content-Length': str(len(encoded))}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        headers.update(extra or {})
        raw = '\r\n'.join([f'{method} {path} HTTP/1.1', *(f'{k}: {v}' for k,v in headers.items()), '', '']).encode() + encoded
        sock = RequestSocket(raw)
        self.handler(sock, ('127.0.0.1', 1), SimpleNamespace(server_port=8100))
        head, output = bytes(sock.output).split(b'\r\n\r\n', 1)
        return int(head.split(b' ')[1]), json.loads(output)

    def test_anonymous_and_forged_identity_cannot_access_data(self):
        for path, method in (('/api/projects', 'GET'), ('/dashboard', 'POST'), ('/projects', 'POST'), ('/api/keys', 'GET')):
            for token in (None, 'bad'):
                self.assertEqual(self.request(path, token=token, method=method)[0], 401)
        self.assertEqual(self.request('/api/projects', token=self.token(), method='GET', extra={'Origin': 'https://evil.test'})[0], 403)
        self.assertEqual(len(self.hosted.services), 0)

    def test_two_users_same_project_id_never_share_memory(self):
        alice, bob = self.token(), self.token('user_bob')
        for token, name in ((alice, 'Alice project'), (bob, 'Bob project')):
            self.assertEqual(self.request('/projects', {'project_id': 'same', 'name': name}, token)[0], 200)
        status, data = self.request('/api/projects', token=bob, method='GET')
        self.assertEqual([p['name'] for p in data['projects']], ['Bob project'])
        fact = {'project_id': 'same', 'scope': 'web/main', 'subject': 'auth', 'predicate': 'method', 'value': 'Alice secret design',
                'source': {'id': 'S1', 'kind': 'developer', 'authority': 'developer', 'title': 'Decision', 'content': 'Alice secret design'}, 'fact_id': 'F1'}
        self.assertEqual(self.request('/remember', fact, alice)[0], 200)
        _, data = self.request('/recall', {'project_id': 'same', 'scope': 'web/main'}, bob)
        self.assertEqual(data['active_facts'], [])
        self.assertEqual(self.request('/history', {'project_id': 'same', 'fact_id': 'F1'}, bob)[0], 404)
        self.assertEqual(self.request('/remember', {**fact, 'owner': 'user_alice'}, bob)[0], 400)
        _, dashboard = self.request('/dashboard', {'project_id': 'same'}, bob)
        self.assertNotIn('Alice secret design', json.dumps(dashboard))

    def test_keys_are_owner_scoped_revocable_and_hash_only(self):
        alice, bob = self.token(), self.token('user_bob')
        status, created = self.request('/account/keys', {'name': 'Laptop'}, alice)
        self.assertEqual(status, 200)
        key = created['token']
        self.assertEqual(self.request('/account/keys', {'name': 'Escalation'}, key)[0], 403)
        self.assertEqual(self.request('/projects', {'project_id': 'keys', 'name': 'Key project'}, key)[0], 200)
        self.assertEqual(self.request('/api/keys', token=key, method='GET')[0], 403)
        _, rows = self.request('/api/keys', token=alice, method='GET')
        self.assertNotIn(key, json.dumps(rows))
        stored = self.hosted.auth.query('MATCH (k:AccessKey) RETURN properties(k)', {})
        self.assertNotIn(key, json.dumps(stored))
        self.request('/account/keys/revoke', {'id': created['id']}, bob)
        self.assertEqual(self.request('/api/projects', token=key, method='GET')[0], 200)
        self.request('/account/keys/revoke', {'id': created['id']}, alice)
        self.assertEqual(self.request('/api/projects', token=key, method='GET')[0], 401)
