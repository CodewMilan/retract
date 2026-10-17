"""Run fresh evaluation checks and create an evidence bundle, without publishing.

Default is offline. --live additionally runs the isolated Docker/database gate,
Groq's 16 declared cases, SDK/PostgreSQL checks, and real Chromium UI checks.
A real coding session, generated feature verification, public repository, and
working demo recording still require independent evidence and review.
"""
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_release import scan


def source_manifest(root=ROOT):
    paths = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root,
                           capture_output=True, check=True, timeout=15).stdout.split(b'\0')
    manifest = {}
    for raw in sorted(set(paths) - {b''}):
        relative = raw.decode('utf-8', errors='surrogateescape')
        path = root / relative
        if path.is_file() and not path.is_symlink():
            manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return {'sha256': digest, 'files': manifest}


def run_check(command, logfile, *, timeout=120):
    try:
        with logfile.open('w') as output:
            completed = subprocess.run(command, cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT / 'src'), 'PYTHON': sys.executable},
                                       stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
        return {'status': 'passed' if completed.returncode == 0 else 'blocked_or_failed', 'exit_code': completed.returncode,
                'log': logfile.name}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'status': 'blocked_or_failed', 'error_type': type(exc).__name__, 'log': logfile.name}


def read_report(path):
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Report must be an object')
    return value


def render_report(report):
    lines = ['# RETRACT evaluation run', '', f"Recorded: {report['recorded_at']}", '',
             f"Run status: **{report['status']}**. Submission readiness: **not verified**.", '',
             '| Check | Result |', '| --- | --- |']
    lines.extend(f"| {name} | {value['status']} |" for name, value in report['checks'].items())
    lines.extend(['', '## Measured metrics', ''])
    metrics = report['metrics']
    memory = metrics['structured_memory']
    if memory is None:
        lines.append('Real graph metrics were not measured. Wrong invalidations, stale retrieval, plan precision/recall, and graph latency are unknown.')
    else:
        lines.extend([f"- Structured cases passed: {memory['passed_cases']}/{memory['total_cases']}.",
                      f"- Wrong invalidations: {memory['wrong_invalidations']}.",
                      f"- Stale retrievals: {memory['stale_retrievals']} / {memory['fact_observations']} observed facts.",
                      f"- Affected-plan precision/recall: {memory['affected_plans']['precision']} / {memory['affected_plans']['recall']}.",
                      f"- Latency (milliseconds, small service/storage fixture): `{json.dumps(memory['latency_ms'], sort_keys=True)}`."])
    model = metrics['live_model']
    if model is None:
        lines.extend(['', 'Live model classification accuracy, inference latency, and token usage were not measured.'])
    else:
        lines.extend(['', f"Live model cases evaluated: {model['evaluated_cases']}/{model['total_cases']}; classification accuracy: {model['classification_accuracy']}.",
                      'See phase2.json for per-case policy outcomes, errors, latency, and provider-reported usage. Partial results are not a complete pass.'])
    lines.extend(['', '## Remaining evidence', '', 'A real coding-client recall, generated feature tests, a working demo recording, repository visibility, and final submission review remain unverified.', '',
                  'The JSON includes exact source/artifact hashes and environment versions. Controlled unit fixtures are not graph or model measurements. No hosted deployment or comparative benchmark is claimed.', ''])
    return '\n'.join(lines)


def run(report_dir, *, live=False):
    if report_dir.exists() and any(report_dir.iterdir()):
        raise ValueError('Use a new or empty report directory; prior reports are never reused')
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': 1, 'phase': 5, 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'mode': 'live' if live else 'offline', 'python': platform.python_version(),
              'platform': platform.platform(), 'machine': platform.machine(), 'checks': {},
              'metrics': {'structured_memory': None, 'live_model': None},
              'submission_ready': False,
              'unverified_evidence': ['real_coding_client_and_generated_feature', 'working_demo_video', 'public_repository', 'final_human_review']}
    report['source_before'] = source_manifest()
    report['installed_packages'] = {}
    for package in ('falkordb', 'psycopg', 'mcp', 'setuptools'):
        try:
            report['installed_packages'][package] = version(package)
        except PackageNotFoundError:
            report['installed_packages'][package] = None
    commands = {
        'python_regression': [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
        'javascript': ['node', '--test', 'tests/dashboard-model.test.mjs', 'tests/account-client.test.mjs'],
    }
    if live:
        commands.update({
            'database_and_restart': [sys.executable, 'scripts/verify_phase1.py', '--report-dir', str(report_dir / 'phase1')],
            'live_model': [sys.executable, 'scripts/verify_phase2.py', '--live', '--report', str(report_dir / 'phase2.json')],
            'sdk_and_postgres': [sys.executable, 'scripts/verify_phase3.py', '--sdk', '--postgres', '--report', str(report_dir / 'phase3.json')],
            'browser': [sys.executable, 'scripts/verify_phase4.py', '--browser', '--report', str(report_dir / 'phase4.json')],
            'account_settings_browser': [sys.executable, 'scripts/verify_account_settings.py', '--browser', '--report', str(report_dir / 'account-settings.json')],
        })
    try:
        for name, command in commands.items():
            print(f'Phase 5: {name}', flush=True)
            report['checks'][name] = run_check(command, report_dir / (name + '.log'), timeout=900 if name in ('database_and_restart', 'live_model') else 240)
        release = scan()
        (report_dir / 'release-scan.json').write_text(json.dumps(release, indent=2) + '\n')
        report['checks']['release_patterns'] = {'status': release['status'], 'report': 'release-scan.json'}
        graph = read_report(report_dir / 'phase1/memory-evaluation.json')
        if graph and isinstance(graph.get('evaluation'), dict) and graph['evaluation'].get('storage_kind') == 'falkordb':
            report['metrics']['structured_memory'] = graph['evaluation']
        model = read_report(report_dir / 'phase2.json')
        if model and isinstance(model.get('live_evaluation'), dict):
            report['metrics']['live_model'] = model['live_evaluation']
        report['source_after'] = source_manifest()
        report['checks']['source_unchanged_during_checks'] = {'status': 'passed' if report['source_before'] == report['source_after'] else 'failed'}
        passed = all(check['status'] == 'passed' for check in report['checks'].values())
        report['status'] = ('live_checks_passed_manual_evidence_unverified' if live else 'offline_passed_live_unverified') if passed else 'blocked_or_failed'
        returncode = 0 if passed else 1
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report.update(status='blocked_or_failed', error_type=type(exc).__name__)
        returncode = 1
    report['artifacts'] = {str(path.relative_to(report_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(report_dir.rglob('*')) if path.is_file() and path.name not in ('phase5.json', 'RESULTS.md')}
    (report_dir / 'phase5.json').write_text(json.dumps(report, indent=2) + '\n')
    (report_dir / 'RESULTS.md').write_text(render_report(report))
    print(f"Phase 5: {report['status']}. Results: {report_dir / 'RESULTS.md'}")
    return returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Run actual database/model/browser checks; requires installed dependencies and demo PostgreSQL')
    parser.add_argument('--report-dir', type=Path, default=ROOT / 'reports' / ('phase5-' + uuid4().hex[:12]))
    args = parser.parse_args()
    try:
        return run(args.report_dir.resolve(), live=args.live)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Phase 5 could not start: {type(exc).__name__}: use a writable empty report directory and a Git checkout', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
