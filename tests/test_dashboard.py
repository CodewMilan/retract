from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retract.activity import ActivityJournal
from retract.api import dispatch, make_handler
from retract.graph import DatabaseUnavailable, GraphStore
from retract.models import PlanInput, RememberInput, ValidationError, parse
from retract.service import MemoryService
from tests.support import ModelStore
from tests.test_http import RequestSocket
from tests.test_policy import confirmed_update


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.store = ModelStore()
        self.service = MemoryService(self.store)
        fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/demo-seed.json').read_text())
        self.service.create_project(**fixture['project'])
        for action in fixture['actions']:
            if action['route'] == 'remember':
                self.service.remember(parse(RememberInput, action['body']))
            else:
                self.service.record_plan(parse(PlanInput, action['body']))

    def test_readonly_snapshot_shows_replacements_evidence_and_actual_paths(self):
        self.service.process_update(confirmed_update())
        before = self.service.project('account-settings')['revision']
        snapshot = self.service.dashboard('account-settings', 'web-client/main')
        self.assertEqual({f['id']: f['status'] for f in snapshot['facts']}, {'F1': 'superseded', 'F5': 'active'})
        self.assertEqual(snapshot['counts']['affected'], 1)
        self.assertEqual(snapshot['explanation_paths'][0]['fact']['id'], 'F1')
        self.assertEqual(snapshot['explanation_paths'][0]['event']['id'], 'U1')
        self.assertEqual(snapshot['updates'][0]['result']['accepted_fact_ids'], ['F5'])
        self.assertTrue(any(e['relationship'] == 'SUPPORTS' and e['from']['id'] == 'S-U1' for e in snapshot['edges']))
        self.assertNotIn('fingerprint', json.dumps(snapshot))
        self.assertNotIn('result_json', json.dumps(snapshot))
        self.assertEqual(self.service.project('account-settings')['revision'], before)

    def test_scope_and_project_isolation(self):
        self.service.create_project('other', 'Other')
        self.assertEqual(self.service.dashboard('other')['facts'], [])
        snapshot = self.service.dashboard('account-settings', 'account-service/main')
        self.assertEqual({f['id'] for f in snapshot['facts']}, {'F3', 'F4'})
        self.assertEqual(snapshot['updates'], [])
        self.assertNotIn('F1', json.dumps(snapshot['edges']))

    def test_cross_scope_plan_paths_include_the_actual_update_scope(self):
        self.service.record_plan(PlanInput('account-settings', 'separate/scope', 'Use the auth decision', ['F1'], 'cross-scope'))
        self.service.process_update(confirmed_update())
        snapshot = self.service.dashboard('account-settings', 'separate/scope')
        self.assertEqual(snapshot['updates'], [])
        self.assertEqual(snapshot['explanation_paths'][0]['event']['scope'], 'web-client/main')
        self.assertEqual(snapshot['explanation_paths'][0]['plan']['id'], 'cross-scope')

    def test_proposal_remains_separate_and_does_not_retire_facts(self):
        self.service.process_update(replace(confirmed_update(), classification='proposal'))
        snapshot = self.service.dashboard('account-settings')
        self.assertEqual(snapshot['counts']['pending'], 1)
        self.assertEqual(snapshot['counts']['active'], 4)
        self.assertEqual(snapshot['counts']['superseded'], 0)
        self.assertEqual(snapshot['plans'], [])

    def test_inputs_are_validated(self):
        for body in ({}, {'project_id': 'account-settings', 'scope': ''}, {'project_id': 'account-settings', 'extra': True}):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                dispatch(self.service, '/dashboard', body)

    def request(self, route, method='GET', body=None, headers=None):
        raw = json.dumps(body or {}).encode()
        values = {'Host': '127.0.0.1:8100', 'Content-Type': 'application/json', 'Content-Length': str(len(raw)), **(headers or {})}
        head = '\r\n'.join([f'{method} {route} HTTP/1.1', *(f'{key}: {value}' for key, value in values.items()), '', ''])
        transport = RequestSocket(head.encode() + raw)
        make_handler(self.service)(transport, ('127.0.0.1', 1234), SimpleNamespace(server_port=8100))
        header, content = bytes(transport.output).split(b'\r\n\r\n', 1)
        return int(header.split(b' ')[1]), header.decode(), content

    def test_static_resources_are_served_with_strict_csp_and_allowlist(self):
        for path, mime in [('/', 'text/html'), ('/assets/dashboard.mjs', 'text/javascript'), ('/assets/dashboard-model.mjs', 'text/javascript'), ('/assets/dashboard.css', 'text/css')]:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn(mime, headers)
                self.assertIn("script-src 'self'", headers)
                self.assertIn("frame-ancestors 'none'", headers)
                self.assertIn('no-store', headers)
                self.assertGreater(len(body), 100)
        for path in ['/assets/../service.py', '/assets/%2e%2e/service.py', '/brand.md', '/?file=.env']:
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request('/', headers={'Origin': 'https://external.test'})[0], 403)

    def test_projects_and_snapshot_use_the_existing_service(self):
        self.assertEqual(json.loads(self.request('/api/projects')[2])['projects'][0]['id'], 'account-settings')
        status, _, raw = self.request('/dashboard', 'POST', {'project_id': 'account-settings'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['project']['revision'], 5)
        self.assertEqual(self.service.activity.read('account-settings'), [])

    def test_actual_request_activity_records_success_and_error_without_content(self):
        self.request('/recall', 'POST', {'project_id': 'account-settings', 'scope': 'web-client/main'}, {'X-Retract-Client': 'mcp'})
        self.request('/remember', 'POST', {'project_id': 'account-settings', 'source': 'PRIVATE_CONTENT'}, {'X-Retract-Client': 'dashboard'})
        entries = self.service.dashboard('account-settings')['activity']
        self.assertEqual([entry['status'] for entry in entries], [400, 200])
        self.assertEqual([entry['client'] for entry in entries], ['dashboard', 'mcp'])
        self.assertNotIn('PRIVATE_CONTENT', json.dumps(entries))
        self.assertEqual(MemoryService(self.store).dashboard('account-settings')['activity'], [])

    def test_storage_failure_returns_503_but_shell_still_loads(self):
        with patch.object(self.store, 'dashboard_snapshot', side_effect=DatabaseUnavailable('Storage unavailable')):
            with self.assertLogs('retract.api', level='ERROR'):
                self.assertEqual(self.request('/dashboard', 'POST', {'project_id': 'account-settings'})[0], 503)
            self.assertEqual(self.request('/')[0], 200)

    def test_bounded_panels_report_totals_and_truncation(self):
        for index in range(205):
            self.store.put('Fact', {'id': f'fact-{index}', 'project_id': 'account-settings', 'scope': 'lots', 'subject': 'key', 'predicate': str(index), 'value': 'x', 'status': 'active'})
        snapshot = self.service.dashboard('account-settings', 'lots')
        self.assertEqual(snapshot['counts']['active'], 205)
        self.assertEqual(len(snapshot['facts']), 200)
        self.assertTrue(snapshot['truncated']['active'])

    def test_graph_reader_bounds_queries_and_projects_all_edge_endpoints(self):
        # Query-shape/projection check only. Real Cypher has a separate opt-in test.
        def query(statement, params):
            if 'count(n)' in statement:
                return [[0]]
            if 'RETURN type(r)' in statement:
                self.assertIn('LIMIT 1001', statement)
                return [['BASED_ON', {'id': 'event', 'fingerprint': 'secret', 'result_json': 'secret'}, {'id': 'source', 'content': 'literal <script>'}]]
            return []
        store = GraphStore(object())
        with patch.object(store, 'query', side_effect=query):
            result = store.dashboard_snapshot('project')
        self.assertEqual(result['edges'][0]['from'], {'id': 'event'})
        self.assertEqual(result['edges'][0]['to']['content'], 'literal <script>')


class ActivityTests(unittest.TestCase):
    def test_retention_is_bounded_scoped_and_defensive(self):
        journal = ActivityJournal(2)
        journal.record('/recall', {'project_id': 'other'}, 200, 'mcp', 1)
        journal.record('/recall', {'project_id': 'project', 'scope': 'a'}, 200, 'mcp', 2)
        journal.record('/history', {'project_id': 'project'}, 404, 'api', 3)
        self.assertEqual(len(journal.entries), 2)
        self.assertEqual(len(journal.read('project', 'b')), 1)
        self.assertEqual(journal.read('other'), [])
        journal.read('project')[0]['status'] = 0
        self.assertEqual(journal.read('project')[0]['status'], 404)
