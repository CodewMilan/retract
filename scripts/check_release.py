"""Bounded secret-pattern scan of distributable files and reachable Git blobs.

Reports locations and pattern names only. This is not an exhaustive security or
license audit. Ignored local .env/reports/venvs are outside the public-file scope.
"""
from pathlib import Path
import argparse
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 2 * 1024 * 1024
PATTERNS = {
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'groq_key': re.compile(r'\bgsk_[A-Za-z0-9]{32,}\b'),
    'openai_key': re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b'),
    'github_token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'aws_access_key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential_url': re.compile(r'\b(?:postgres(?:ql)?|redis|rediss|https?)://[^\s/:]+:([^\s/@]+)@'),
}


def scan_content(location, content):
    if b'\0' in content:
        return [], 'binary_not_scanned'
    source = content.decode('utf-8', errors='replace')
    findings = []
    for kind, pattern in PATTERNS.items():
        for match in pattern.finditer(source):
            # Exactly the publicly documented synthetic localhost demo credential.
            if kind == 'credential_url' and match.group(0) == 'postgresql://retract_demo:local_demo_only@':
                continue
            findings.append({'location': location, 'line': source.count('\n', 0, match.start()) + 1, 'pattern': kind})
    return findings, 'text_scanned'


def git(root, *args, input=None):
    result = subprocess.run(['git', *args], cwd=root, input=input, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Git inventory could not be inspected')
    return result.stdout


def scan(root=ROOT, *, history=True):
    root = root.resolve()
    findings, excluded, scanned = [], [], 0
    paths = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0')
    for value in sorted(set(paths) - {b''}):
        relative = value.decode('utf-8', errors='surrogateescape')
        path = root / relative
        if path.is_symlink():
            excluded.append({'location': relative, 'reason': 'symlink_not_followed'})
            continue
        if not path.is_file():
            continue
        if path.name == '.env' or (path.name.startswith('.env.') and path.name != '.env.example'):
            findings.append({'location': relative, 'line': None, 'pattern': 'environment_file_in_public_inventory'})
        if path.stat().st_size > MAX_FILE:
            excluded.append({'location': relative, 'reason': 'over_size_limit'})
            continue
        found, coverage = scan_content(relative, path.read_bytes())
        findings.extend(found)
        if coverage != 'text_scanned':
            excluded.append({'location': relative, 'reason': coverage})
        else:
            scanned += 1
    blobs = 0
    if history:
        if git(root, 'rev-parse', '--is-shallow-repository').strip() == b'true':
            excluded.append({'location': 'git-history', 'reason': 'shallow_checkout'})
        objects = git(root, 'rev-list', '--objects', '--all', '--no-object-names').splitlines()
        if objects:
            inventory = git(root, 'cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)', input=b'\n'.join(objects) + b'\n')
            for line in inventory.splitlines():
                sha, kind, size = line.decode().split()
                if kind != 'blob':
                    continue
                location = 'git-blob:' + sha
                if int(size) > MAX_FILE:
                    excluded.append({'location': location, 'reason': 'over_size_limit'})
                    continue
                found, coverage = scan_content(location, git(root, 'cat-file', 'blob', sha))
                findings.extend(found)
                if coverage != 'text_scanned':
                    excluded.append({'location': location, 'reason': coverage})
                else:
                    blobs += 1
    return {'status': 'findings' if findings else 'incomplete' if excluded else 'passed',
            'scope': 'Git tracked and nonignored files, plus reachable Git blobs. Pattern scan only; binary/oversize/symlink exclusions are explicit.',
            'worktree_text_files': scanned, 'history_text_blobs': blobs, 'findings': findings, 'exclusions': excluded}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/release-scan.json')
    parser.add_argument('--no-history', action='store_true')
    args = parser.parse_args()
    try:
        result = scan(history=not args.no_history)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        result = {'status': 'blocked_or_failed', 'error': 'Could not complete public-file inventory/scan'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Release pattern scan: {result['status']}. Report: {args.report}")
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
