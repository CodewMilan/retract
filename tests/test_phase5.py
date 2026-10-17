from copy import deepcopy
from dataclasses import replace
from itertools import count
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from scripts import check_release, evaluate_memory, verify_phase5
from tests.support import ModelStore


class MemoryEvaluationTests(unittest.TestCase):
    def evaluate(self, store=None):
        ticks = count(step=1_000_000)
        return evaluate_memory.evaluate(store or ModelStore(), storage_kind='test_model', clock=lambda: next(ticks))

    def test_declared_structured_cases_and_controls_pass_without_claiming_live_metrics(self):
        result = self.evaluate()
        self.assertEqual(result['total_cases'], 14)
        self.assertEqual(result['passed_cases'], 14)
        self.assertEqual(result['wrong_invalidations'], 0)
        self.assertEqual(result['stale_retrievals'], 0)
        self.assertEqual(result['affected_plans']['precision'], 1)
        self.assertEqual(result['affected_plans']['recall'], 1)
        self.assertIsNone(result['latency_ms'])
        self.assertIsNone(result['classification_accuracy'])
        self.assertIsNone(result['token_usage'])
        for row in result['results']:
            self.assertTrue(row['passed'], row)

    def test_protected_fact_corruption_is_counted_and_fails(self):
        class CorruptingStore(ModelStore):
            def record_event(self, project, revision, source, event, new_fact, target):
                super().record_event(project, revision, source, event, new_fact, target)
                protected = self.get('Fact', project, 'F4')
                if protected:
                    protected['value'] = 'any profile'
                    self.put('Fact', protected)
        result = self.evaluate(CorruptingStore())
        self.assertFalse(result['passed'])
        self.assertGreater(result['wrong_invalidations'], 0)

    def test_superseded_fact_leaking_into_recall_is_counted_and_fails(self):
        class StaleStore(ModelStore):
            def recall(self, project, scope, subjects):
                result = super().recall(project, scope, subjects)
                old = self.get('Fact', project, 'F1')
                if old and old['status'] == 'superseded' and old['scope'] == scope:
                    result['active_facts'].append(old)
                return result
        result = self.evaluate(StaleStore())
        self.assertFalse(result['passed'])
        self.assertGreater(result['stale_retrievals'], 0)

    def test_false_plan_warning_reduces_precision(self):
        class OverflaggingStore(ModelStore):
            def record_event(self, project, revision, source, event, new_fact, target):
                super().record_event(project, revision, source, event, new_fact, target)
                if new_fact:
                    plan = self.get('Plan', project, 'P-safe')
                    plan['status'] = 'needs_review'
                    self.put('Plan', plan)
        result = self.evaluate(OverflaggingStore())
        self.assertFalse(result['passed'])
        self.assertLess(result['affected_plans']['precision'], 1)
        self.assertGreater(result['affected_plans']['false_positive'], 0)

    def test_correct_ids_with_an_incorrect_accepted_value_cannot_pass(self):
        class WrongValueStore(ModelStore):
            def record_event(self, project, revision, source, event, new_fact, target):
                if new_fact:
                    new_fact = {**new_fact, 'value': 'wrong authentication'}
                super().record_event(project, revision, source, event, new_fact, target)
        result = self.evaluate(WrongValueStore())
        self.assertFalse(result['passed'])
        self.assertTrue(any(not row['checks']['current_fact_values'] for row in result['results']))

    def test_missing_plan_warning_reduces_recall(self):
        class UnderflaggingStore(ModelStore):
            def record_event(self, project, revision, source, event, new_fact, target):
                super().record_event(project, revision, source, event, new_fact, target)
                if new_fact:
                    plan = self.get('Plan', project, 'P-cross')
                    plan['status'] = 'current'
                    self.put('Plan', plan)
        result = self.evaluate(UnderflaggingStore())
        self.assertFalse(result['passed'])
        self.assertLess(result['affected_plans']['recall'], 1)

    def test_empty_denominators_and_percentile_are_explicit(self):
        self.assertEqual(evaluate_memory.score([], [])['precision'], None)
        self.assertEqual(evaluate_memory.score([], [])['recall'], None)
        self.assertIsNone(evaluate_memory.distribution([]))
        self.assertEqual(evaluate_memory.distribution([1, 2, 3, 4]), {'samples': 4, 'p50': 2.5, 'p95': 4})

    def test_missing_database_dependency_fails_with_null_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'evaluation.json'
            with patch.dict('sys.modules', {'falkordb': None}):
                self.assertEqual(evaluate_memory.run(report), 1)
            result = json.loads(report.read_text())
            self.assertEqual(result['status'], 'blocked')
            self.assertIsNone(result['evaluation'])
            self.assertTrue(result['graph_name'].startswith('retract-eval-'))

    def test_only_the_generated_graph_is_deleted_after_success(self):
        client = MagicMock()
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict('sys.modules', {'falkordb': SimpleNamespace(FalkorDB=lambda **kwargs: client)}), \
             patch.dict('os.environ', {'FALKORDB_GRAPH': 'important-application-graph'}), \
             patch.object(evaluate_memory, 'version', return_value='test-version'), \
             patch.object(evaluate_memory, 'evaluate', return_value={'passed': True}):
            path = Path(directory) / 'result.json'
            self.assertEqual(evaluate_memory.run(path), 0)
            result = json.loads(path.read_text())
        name = client.select_graph.call_args.args[0]
        self.assertTrue(name.startswith('retract-eval-'))
        self.assertNotEqual(name, 'important-application-graph')
        client.select_graph.return_value.delete.assert_called_once_with()
        client.connection.close.assert_called_once_with()
        self.assertEqual(result['graph_retention'], 'deleted_owned_graph')

    def test_failed_evaluation_preserves_owned_graph(self):
        client = MagicMock()
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict('sys.modules', {'falkordb': SimpleNamespace(FalkorDB=lambda **kwargs: client)}), \
             patch.object(evaluate_memory, 'version', return_value='test-version'), \
             patch.object(evaluate_memory, 'evaluate', return_value={'passed': False}):
            path = Path(directory) / 'result.json'
            self.assertEqual(evaluate_memory.run(path), 1)
            result = json.loads(path.read_text())
        client.select_graph.return_value.delete.assert_not_called()
        self.assertEqual(result['graph_retention'], 'preserved')

    def test_cleanup_failure_is_not_reported_as_success(self):
        client = MagicMock()
        client.select_graph.return_value.delete.side_effect = OSError('sensitive diagnostics')
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict('sys.modules', {'falkordb': SimpleNamespace(FalkorDB=lambda **kwargs: client)}), \
             patch.object(evaluate_memory, 'version', return_value='test-version'), \
             patch.object(evaluate_memory, 'evaluate', return_value={'passed': True}):
            path = Path(directory) / 'result.json'
            self.assertEqual(evaluate_memory.run(path), 1)
            result = json.loads(path.read_text())
        self.assertEqual(result['status'], 'cleanup_failed')
        self.assertNotIn('sensitive diagnostics', json.dumps(result))


class ReleaseScanTests(unittest.TestCase):
    def test_secret_findings_retain_only_location_kind_and_line(self):
        secret = 'gsk_' + 'A' * 40
        findings, coverage = check_release.scan_content('source.py', ('prefix\n' + secret).encode())
        self.assertEqual(coverage, 'text_scanned')
        self.assertEqual(findings, [{'location': 'source.py', 'line': 2, 'pattern': 'groq_key'}])
        self.assertNotIn(secret, json.dumps(findings))

    def test_supported_patterns_and_public_demo_credential(self):
        examples = [('private_key', '-----BEGIN ' + 'PRIVATE KEY-----'), ('github_token', 'ghp_' + 'a' * 36),
                    ('aws_access_key', 'AKIA' + 'A' * 16), ('openai_key', 'sk-proj-' + 'a' * 40),
                    ('credential_url', 'postgresql://' + 'user:private@host/db')]
        for kind, value in examples:
            with self.subTest(kind=kind):
                self.assertIn(kind, [r['pattern'] for r in check_release.scan_content('test', value.encode())[0]])
        self.assertEqual(check_release.scan_content('demo', b'postgresql://retract_demo:local_demo_only@127.0.0.1/db')[0], [])

    def test_removed_secret_in_real_git_history_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
            git('init', '-q')
            secret = 'gsk_' + 'B' * 40
            (root / 'old.txt').write_text(secret)
            git('add', 'old.txt')
            git('-c', 'user.name=Evaluation test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Synthetic secret fixture')
            (root / 'old.txt').write_text('removed')
            git('add', 'old.txt')
            git('-c', 'user.name=Evaluation test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Remove fixture')
            result = check_release.scan(root)
            self.assertEqual(result['status'], 'findings')
            self.assertTrue(any(f['location'].startswith('git-blob:') for f in result['findings']))
            self.assertNotIn(secret, json.dumps(result))

    def test_binary_and_symlink_exclusions_cannot_pass_a_complete_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True, capture_output=True)
            (root / 'binary').write_bytes(b'\0binary')
            (root / 'link').symlink_to('/etc/hosts')
            result = check_release.scan(root)
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(len(result['exclusions']), 2)

    def test_tracked_env_file_is_flagged_without_reading_ignored_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True, capture_output=True)
            (root / '.gitignore').write_text('.env\n')
            (root / '.env').write_text('PRIVATE=localonly')
            self.assertEqual(check_release.scan(root)['status'], 'passed')
            subprocess.run(['git', 'add', '-f', '.env'], cwd=root, check=True, capture_output=True)
            self.assertEqual(check_release.scan(root)['findings'][0]['pattern'], 'environment_file_in_public_inventory')


class EvidenceBundleTests(unittest.TestCase):
    def test_past_results_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'phase2.json').write_text('{"status":"passed"}')
            with self.assertRaisesRegex(ValueError, 'prior reports'):
                verify_phase5.run(path)

    def test_offline_bundle_keeps_all_live_metrics_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(verify_phase5, 'run_check', return_value={'status': 'passed'}), \
                 patch.object(verify_phase5, 'scan', return_value={'status': 'passed'}), \
                 patch.object(verify_phase5, 'source_manifest', return_value={'sha256': 'same', 'files': {}}):
                self.assertEqual(verify_phase5.run(root), 0)
            report = json.loads((root / 'phase5.json').read_text())
            self.assertFalse(report['submission_ready'])
            self.assertEqual(report['metrics'], {'structured_memory': None, 'live_model': None})
            self.assertIn('not measured', (root / 'RESULTS.md').read_text())

    def test_failed_checks_remain_failures_and_source_changes_are_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(verify_phase5, 'run_check', return_value={'status': 'blocked_or_failed'}), \
                 patch.object(verify_phase5, 'scan', return_value={'status': 'findings'}), \
                 patch.object(verify_phase5, 'source_manifest', side_effect=[{'sha256': 'before'}, {'sha256': 'after'}]):
                self.assertEqual(verify_phase5.run(root), 1)
            report = json.loads((root / 'phase5.json').read_text())
            self.assertEqual(report['checks']['source_unchanged_during_checks']['status'], 'failed')
            self.assertEqual(report['status'], 'blocked_or_failed')

    def test_missing_child_executable_is_a_failed_check(self):
        with tempfile.TemporaryDirectory() as directory:
            result = verify_phase5.run_check(['no-such-executable-retract-evaluation'], Path(directory) / 'log')
            self.assertEqual(result['status'], 'blocked_or_failed')

    def test_failed_live_graph_report_keeps_metrics_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def checked(command, logfile, **kwargs):
                if 'scripts/verify_phase1.py' in command:
                    (root / 'phase1').mkdir()
                    (root / 'phase1/memory-evaluation.json').write_text('{"evaluation": null, "status": "blocked"}')
                return {'status': 'blocked_or_failed'}
            with patch.object(verify_phase5, 'run_check', side_effect=checked), \
                 patch.object(verify_phase5, 'scan', return_value={'status': 'passed'}), \
                 patch.object(verify_phase5, 'source_manifest', return_value={'sha256': 'same', 'files': {}}):
                self.assertEqual(verify_phase5.run(root, live=True), 1)
            self.assertIsNone(json.loads((root / 'phase5.json').read_text())['metrics']['structured_memory'])
