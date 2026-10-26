"""Check staged source (or an unpacked source archive) for private runtime files.

This is a small safeguard, not an exhaustive secret scanner.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIRS = {'data', 'backups', '.aws', '.codex', '.agents', '.ssh'}
SKIP_DIRS = {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.pytest_cache'}
PRIVATE_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.dpapi', '.log', '.pem', '.key', '.p12', '.pfx'}
SECRET_PATTERNS = [
    re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{30,}\b'),
    re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
]


def private_path(path: Path) -> bool:
    name = path.name.lower()
    return (
        bool(set(part.lower() for part in path.parts) & PRIVATE_DIRS)
        or path.suffix.lower() in PRIVATE_SUFFIXES
        or bool(re.search(r'\.(?:sqlite3?|db)-(?:wal|shm|journal)$', name))
        or (name.startswith('.env') and name != '.env.example')
        or name in {'credentials.json', 'credentials.tmp', 'server.json', 'instance.lock', 'validation.txt'}
    )


def files_to_scan():
    if (ROOT / '.git').exists():
        listing = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
        for name in listing.decode('utf-8').split('\0'):
            if name:
                content = subprocess.check_output(['git', 'show', ':' + name], cwd=ROOT)
                yield Path(name), content
    else:
        for item in sorted(ROOT.rglob('*')):
            relative = item.relative_to(ROOT)
            if item.is_file() and not set(relative.parts) & SKIP_DIRS:
                yield relative, item.read_bytes()


def main() -> int:
    findings = []
    count = 0
    for path, content in files_to_scan():
        count += 1
        if private_path(path):
            findings.append(f'{path.as_posix()}: private runtime file')
        if content.startswith(b'SQLite format 3\x00'):
            findings.append(f'{path.as_posix()}: SQLite database content')
        try:
            value = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(value.splitlines(), 1):
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                # Report only the location, never echo credentials into logs.
                findings.append(f'{path.as_posix()}:{line_number}: possible credential')
    if not count:
        print('No source files found; stage the intended files before checking.')
        return 1
    if findings:
        print('\n'.join(findings))
        print('Public-tree check failed. Review files locally; do not post secret values.')
        return 1
    print(f'Public-tree check passed ({count} files). Review the diff before publishing.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
