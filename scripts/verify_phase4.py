"""Run offline Phase 4 checks, with optional real browser interactions.

The browser suite uses controlled HTTP responses by default. --live-url adds a
read-only browser check against an already running, seeded service. Real Cypher
remains the opt-in tests.test_integration / Phase 1 runner gate.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--live-url', help='Requires --browser and a running, seeded local service')
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/phase4.json')
    args = parser.parse_args()
    if args.live_url and not args.browser:
        parser.error('--live-url requires --browser')
    report = {'phase': 4, 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'python_tests': 'not_run', 'javascript_tests': 'not_run', 'browser_controlled_network': 'not_run',
              'live_browser': 'not_run', 'real_dashboard_cypher': 'not_verified'}
    result = 1
    try:
        for key, command in [('python_tests', [sys.executable, '-m', 'unittest', 'tests.test_dashboard', '-v']),
                             ('javascript_tests', ['node', '--test', 'tests/dashboard-model.test.mjs'])]:
            completed = subprocess.run(command, cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')}, timeout=60)
            report[key] = 'passed' if completed.returncode == 0 else 'failed'
            if completed.returncode:
                raise RuntimeError(f'{key} failed')
        if args.browser:
            command = ['node', 'tests/dashboard.browser.mjs']
            if args.live_url:
                command += ['--live-url', args.live_url]
            completed = subprocess.run(command, cwd=ROOT, timeout=180)
            report['browser_controlled_network'] = 'passed' if completed.returncode == 0 else 'blocked_or_failed'
            if completed.returncode:
                raise RuntimeError('Browser checks did not pass; inspect missing dependencies, browser availability, and assertion output')
            if args.live_url:
                report['live_browser'] = 'passed'
        report['status'] = 'requested_checks_passed_live_gates_unverified'
        result = 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report.update(status='blocked_or_failed', error=str(exc))
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(f"Phase 4: {report['status']}. Report: {args.report}")
    return result


if __name__ == '__main__':
    raise SystemExit(main())
