"""Verify the settings feature; browser/live PostgreSQL checks are explicit.

Default tests exercise the actual HTTP handler with controlled profile storage.
This does not establish an independent fresh coding-client recall or generation.
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
    parser.add_argument('--live-url', help='With --browser: edit/restore the synthetic Alice profile on a running local demo')
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/account-settings.json')
    args = parser.parse_args()
    if args.live_url and not args.browser:
        parser.error('--live-url requires --browser')
    report = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'feature': 'account_settings',
              'python_http_tests': 'not_run', 'javascript_http_tests': 'not_run',
              'browser_with_test_storage': 'not_run', 'live_postgres_browser': 'not_run',
              'fresh_coding_client_observed': False}
    commands = [('python_http_tests', [sys.executable, '-m', 'unittest', 'tests.test_demo', 'tests.test_account_settings', '-v']),
                ('javascript_http_tests', ['node', '--test', 'tests/account-client.test.mjs'])]
    if args.browser:
        command = ['node', 'tests/account-settings.browser.mjs']
        if args.live_url:
            command += ['--live-url', args.live_url]
        commands.append(('browser_with_test_storage', command))
    success = True
    try:
        for name, command in commands:
            result = subprocess.run(command, cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT / 'src'), 'PYTHON': sys.executable}, timeout=240)
            report[name] = 'passed' if result.returncode == 0 else 'blocked_or_failed'
            if result.returncode:
                success = False
        if args.live_url:
            report['live_postgres_browser'] = report['browser_with_test_storage']
    except (OSError, subprocess.TimeoutExpired) as exc:
        report.update(error_type=type(exc).__name__)
        success = False
    report['status'] = 'requested_checks_passed_live_gates_unverified' if success else 'blocked_or_failed'
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(f"Account settings: {report['status']}. Report: {args.report}")
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
