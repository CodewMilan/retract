"""Measure the declared structured workflow in a disposable FalkorDB graph.

No runtime fake-store fallback. Only a newly generated graph may be deleted.
Failed runs preserve that graph for inspection. Classification is supplied by the
fixture; this evaluation makes no natural-language accuracy or token-use claim.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from retract.graph import GraphStore
from retract.models import ConflictError, PlanInput, RememberInput, UpdateInput, parse
from retract.service import MemoryService


def distribution(samples):
    if not samples:
        return None
    ordered = sorted(samples)
    return {'samples': len(samples), 'p50': round(statistics.median(ordered), 3),
            'p95': round(ordered[math.ceil(len(ordered) * .95) - 1], 3)}


def score(expected_plans, flagged_plans):
    expected, actual = set(expected_plans), set(flagged_plans)
    tp, fp, fn = len(expected & actual), len(actual - expected), len(expected - actual)
    return {'true_positive': tp, 'false_positive': fp, 'false_negative': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None}


def load_cases():
    dataset = json.loads((ROOT / 'fixtures/memory-eval.json').read_text())
    cases = dataset['cases']
    if not cases or len({row['id'] for row in cases}) != len(cases):
        raise ValueError('Evaluation requires nonempty, uniquely named cases')
    return dataset


def evaluate(store, *, storage_kind, clock=time.perf_counter_ns):
    if storage_kind not in ('falkordb', 'test_model'):
        raise ValueError('Declare the actual storage kind')
    dataset = load_cases()
    seed = json.loads((ROOT / 'fixtures/demo-seed.json').read_text())
    results, timing = [], {'update': [], 'recall': [], 'history': [], 'replay': []}
    service = MemoryService(store)

    def timed(kind, action):
        start = clock()
        try:
            return action()
        finally:
            timing[kind].append((clock() - start) / 1_000_000)

    for case in dataset['cases']:
        project = 'eval-' + case['id']
        service.create_project(project, 'Synthetic evaluation: ' + case['id'])
        for action in seed['actions']:
            body = {**deepcopy(action['body']), 'project_id': project}
            if action['route'] == 'remember':
                service.remember(parse(RememberInput, body))
            else:
                service.record_plan(parse(PlanInput, body))
        for plan_id, scope, dependencies in [('P-safe', 'web-client/main', ['F4']),
                                              ('P-empty', 'web-client/main', []),
                                              ('P-cross', 'planning/main', ['F1'])]:
            service.record_plan(PlanInput(project, scope, 'Synthetic dependency control', dependencies, plan_id))
        before = {fact: store.get('Fact', project, fact) for fact in ('F1', 'F2', 'F3', 'F4')}
        body = json.loads((ROOT / 'fixtures' / case.get('fixture', 'confirmed-update.json')).read_text())
        body['project_id'] = project
        changes = case['changes']
        if changes.get('other_project'):
            body['project_id'] = project + '-other'
            service.create_project(body['project_id'], 'Empty isolation control')
        for key in ('classification', 'confirmation', 'scope', 'target_fact_id', 'expected_revision'):
            if key in changes:
                body[key] = changes[key]
        if 'authority' in changes:
            body['source']['authority'] = changes['authority']
        if 'value' in changes:
            body['candidate']['value'] = changes['value']
            body['text'] = 'Confirmed: browser authentication remains ' + changes['value'] + '.'
            body['source']['content'] = body['text']
            body['candidate']['excerpt'] = body['text']
        request = parse(UpdateInput, body)
        original_revision = service.project(request.project_id)['revision']
        row = {'id': case['id'], 'expected_outcome': case.get('expected_outcome'), 'checks': {}}
        outcome = None
        try:
            outcome = timed('update', lambda: service.process_update(request))
            row['outcome'] = outcome['outcome']
            row['checks']['outcome'] = 'expected_error' not in case and outcome['outcome'] == case['expected_outcome']
        except ConflictError:
            row['outcome'] = 'conflict'
            row['checks']['outcome'] = case.get('expected_error') == 'conflict'
        expected_applied = case.get('expected_outcome') == 'applied'
        expected_plans = ['P1', 'P-cross'] if expected_applied else []
        expected_ids = {'F2', 'F3', 'F4', 'F5'} if expected_applied else set(before)
        if outcome:
            row['checks']['reported_effects'] = (outcome['accepted_fact_ids'] == (['F5'] if expected_applied else [])
                and outcome['retired_fact_ids'] == (['F1'] if expected_applied else [])
                and sorted(outcome['flagged_plan_ids']) == sorted(expected_plans))
            history = timed('history', lambda: service.history(request.project_id, event_id=request.event_id))
            row['checks']['event_evidence'] = history['event'] == outcome and history['source']['id'] == request.source.id
        expected_revision = original_revision + (0 if case.get('expected_error') else 1)
        row['checks']['revision'] = service.project(request.project_id)['revision'] == expected_revision
        # Inspect actual stored state, not the IDs claimed by the update result.
        after = {fact: store.get('Fact', project, fact) for fact in before}
        row['wrong_invalidations'] = sum(after[key] != old for key, old in before.items()
                                          if not (expected_applied and key == 'F1'))
        row['checks']['protected_facts'] = row['wrong_invalidations'] == 0
        if expected_applied:
            row['checks']['retired_fact_preserved'] = after['F1'] is not None and after['F1']['status'] == 'superseded' and after['F1']['value'] == before['F1']['value']
        observations, stale, seen = 0, 0, []
        seen_values = {}
        row['checks']['scoped_recall'] = True
        for scope in ('web-client/main', 'cli-client/main', 'account-service/main', 'planning/main'):
            recalled = timed('recall', lambda: service.recall(project, scope))
            for fact in recalled['active_facts']:
                observations += 1
                stored = store.get('Fact', project, fact['id'])
                stale += int(stored is None or stored.get('status') != 'active' or fact.get('status') != 'active')
                row['checks']['scoped_recall'] &= fact.get('project_id') == project and fact.get('scope') == scope and stored == fact
                seen.append(fact['id'])
                seen_values[fact['id']] = fact.get('value')
        row['stale_retrievals'], row['fact_observations'] = stale, observations
        row['checks']['current_fact_ids'] = set(seen) == expected_ids and len(seen) == len(expected_ids)
        expected_values = {key: value['value'] for key, value in before.items() if key in expected_ids}
        if expected_applied:
            expected_values['F5'] = 'HTTP-only cookie sessions'
        row['checks']['current_fact_values'] = seen_values == expected_values
        row['checks']['no_stale_retrieval'] = stale == 0
        snapshot = service.dashboard(project)
        row['checks']['all_fact_ids'] = {fact['id'] for fact in snapshot['facts']} == (set(before) | {'F5'} if expected_applied else set(before))
        row['checks']['event_count'] = len(snapshot['updates']) == (0 if case.get('expected_error') or changes.get('other_project') else 1)
        actual_plans = [plan['id'] for plan in snapshot['plans'] if plan['status'] == 'needs_review']
        row['plan_confusion'] = score(expected_plans, actual_plans)
        row['checks']['plan_status'] = set(actual_plans) == set(expected_plans)
        row['checks']['plan_paths'] = {path['plan']['id'] for path in snapshot['explanation_paths']
            if path['fact']['id'] == 'F1' and path['event']['id'] == request.event_id} == set(expected_plans)
        if expected_applied:
            row['checks']['replacement_history'] = any(edge['relationship'] == 'SUPERSEDES'
                and edge['from']['id'] == 'F5' and edge['to']['id'] == 'F1' for edge in snapshot['edges'])
            row['checks']['source_history'] = {edge['from']['id'] for edge in snapshot['edges']
                if edge['relationship'] == 'SUPPORTS' and edge['to']['id'] in ('F1', 'F5')} == {'S-F1', 'S-U1'}
        if changes.get('other_project'):
            isolated = service.dashboard(request.project_id)
            row['checks']['project_isolation'] = not isolated['facts'] and not isolated['plans']
        followup = case.get('followup')
        if followup and outcome:
            baseline = service.dashboard(project)
            if followup == 'replay':
                replayed = timed('replay', lambda: service.process_update(request))
                row['checks']['exact_replay'] = replayed == outcome
            elif followup == 'collision':
                try:
                    service.process_update(replace(request, text='Different request with same event ID'))
                    row['checks']['event_collision_rejected'] = False
                except ConflictError:
                    row['checks']['event_collision_rejected'] = True
            else:
                late = service.process_update(replace(request, event_id='late-event', replacement_fact_id='late-fact'))
                row['checks']['retired_target_pending'] = late['outcome'] == 'pending' and not late['accepted_fact_ids']
            after_followup = service.dashboard(project)
            row['checks']['followup_preserves_memory'] = (baseline['facts'] == after_followup['facts']
                and baseline['plans'] == after_followup['plans'])
            if followup != 'retired_target':
                row['checks']['followup_no_new_event'] = baseline['updates'] == after_followup['updates'] and baseline['project'] == after_followup['project']
        row['passed'] = all(row['checks'].values())
        results.append(row)
    confusion = {key: sum(row['plan_confusion'][key] for row in results) for key in ('true_positive', 'false_positive', 'false_negative')}
    tp, fp, fn = (confusion[key] for key in ('true_positive', 'false_positive', 'false_negative'))
    confusion.update(precision=tp / (tp + fp) if tp + fp else None, recall=tp / (tp + fn) if tp + fn else None)
    return {'dataset': dataset['version'], 'storage_kind': storage_kind,
            'measurement_scope': 'Small synthetic structured fixture; service/storage calls, not HTTP or model inference. No warmup or concurrency benchmark.',
            'passed': all(row['passed'] for row in results), 'total_cases': len(results),
            'passed_cases': sum(row['passed'] for row in results),
            'wrong_invalidations': sum(row['wrong_invalidations'] for row in results),
            'stale_retrievals': sum(row['stale_retrievals'] for row in results),
            'fact_observations': sum(row['fact_observations'] for row in results),
            'affected_plans': confusion,
            'latency_ms': {key: distribution(value) for key, value in timing.items()} if storage_kind == 'falkordb' else None,
            'classification_accuracy': None, 'token_usage': None, 'results': results}


def run(report_path, *, keep=False):
    graph_name = 'retract-eval-' + uuid4().hex
    report = {'schema_version': 1, 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'python': platform.python_version(), 'status': 'running', 'evaluation': None,
              'graph_name': graph_name, 'database_version': 'not_observed'}
    store = None
    success = False
    try:
        from falkordb import FalkorDB
        report['falkordb_client'] = version('falkordb')
        client = FalkorDB(host=os.getenv('FALKORDB_HOST', '127.0.0.1'), port=int(os.getenv('FALKORDB_PORT', '6380')),
                         password=os.getenv('FALKORDB_PASSWORD') or None, socket_timeout=10, socket_connect_timeout=3)
        store = GraphStore(client.select_graph(graph_name))
        store.client = client
        store.initialize()
        report['fixture_sha256'] = {name: hashlib.sha256((ROOT / 'fixtures' / name).read_bytes()).hexdigest()
            for name in ('memory-eval.json', 'demo-seed.json', 'confirmed-update.json', 'proposal.json')}
        report['evaluation'] = evaluate(store, storage_kind='falkordb')
        success = report['evaluation']['passed']
        report['status'] = 'passed' if success else 'failed'
    except (ImportError, PackageNotFoundError):
        report.update(status='blocked', error='FalkorDB client unavailable; install the project in the active environment')
    except Exception as exc:
        # Database errors can contain secrets; expose only the error type.
        report.update(status='blocked_or_failed', error=f'{type(exc).__name__}: evaluation could not complete; check database availability and local diagnostics')
    finally:
        if store:
            if success and not keep:
                try:
                    store.graph.delete()
                    report['graph_retention'] = 'deleted_owned_graph'
                except Exception:
                    report.update(status='cleanup_failed', graph_retention='preserved', cleanup_error='Could not delete the owned evaluation graph')
                    success = False
            else:
                report['graph_retention'] = 'preserved'
            try:
                store.close()
            except Exception:
                report.update(status='cleanup_failed', close_error='Could not close evaluation client')
                success = False
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        print(f"Memory evaluation: {report['status']}. Report: {report_path}")
    return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/memory-evaluation.json')
    parser.add_argument('--keep', action='store_true', help='Keep this run\'s isolated graph after success')
    args = parser.parse_args()
    return run(args.report, keep=args.keep)


if __name__ == '__main__':
    raise SystemExit(main())
