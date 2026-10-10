#!/usr/bin/env python3
"""User-operated hidden password entry. Does not connect or restart services."""
import argparse
import getpass
import os
from pathlib import Path
import re
import sys
import tempfile

KEYS = ('SMTP_PASSWORD', 'IMAP_PASSWORD')
CONFIG = Path(__file__).resolve().parents[1] / '.env'
GMAIL_DEFAULTS = {
    'SMTP_HOST': 'smtp.gmail.com', 'SMTP_PORT': '587', 'SMTP_STARTTLS': 'true',
    'SMTP_USERNAME': 'krishnadvaipayana2003@gmail.com',
    'SMTP_FROM': 'krishnadvaipayana2003@gmail.com',
    'IMAP_HOST': 'imap.gmail.com', 'IMAP_PORT': '993',
    'IMAP_USERNAME': 'krishnadvaipayana2003@gmail.com',
}


def save_gmail_defaults(path):
    if path.is_symlink():
        raise ValueError('Use a regular local settings file.')
    from dotenv import dotenv_values
    values = dotenv_values(path, interpolate=False) if path.exists() else {}
    missing = {key: value for key, value in GMAIL_DEFAULTS.items() if not values.get(key)}
    if not missing:
        return
    lines = path.read_text().splitlines() if path.exists() else []
    lines.extend(f'{key}={value}' for key, value in missing.items())
    fd, temporary = tempfile.mkstemp(prefix='.email-config-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(lines) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_password(path, password):
    if not password or any(c in password for c in '\r\n\x00'):
        raise ValueError('Enter a nonempty single-line app password.')
    if path.is_symlink():
        raise ValueError('Local config is a symlink; use your existing secret manager instead.')
    existing = path.read_text() if path.exists() else ''
    # Preserve unrelated settings/comments. Replace all duplicate password entries.
    pattern = re.compile(r'^\s*(?:export\s+)?(?:SMTP_PASSWORD|IMAP_PASSWORD)\s*=')
    lines = [line for line in existing.splitlines() if not pattern.match(line)]
    from dotenv import dotenv_values
    values = dotenv_values(path, interpolate=False) if path.exists() else {}
    lines.extend(f'{key}={value}' for key, value in GMAIL_DEFAULTS.items() if not values.get(key))
    value = '"' + password.replace('\\', '\\\\').replace('"', '\\"') + '"'
    lines.extend(key + '=' + value for key in KEYS)
    fd, temporary = tempfile.mkstemp(prefix='.email-config-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(lines) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def readiness(path):
    if path.is_symlink():
        raise ValueError('Local config is a symlink; use your existing secret manager instead.')
    from dotenv import dotenv_values
    values = dotenv_values(path) if path.exists() else {}
    # Boolean output only. Never emit config values, passwords or exceptions containing them.
    for key in ('SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'IMAP_HOST', 'IMAP_USERNAME', 'IMAP_PASSWORD'):
        print(key + ' configured: ' + ('yes' if values.get(key) else 'no'))
    print('These flags confirm configuration presence, not a successful email connection.')


def main():
    parser = argparse.ArgumentParser(description='Enter your Gmail app password locally; input is hidden.')
    parser.add_argument('--check', action='store_true', help='Print configuration presence flags only; no network calls.')
    args = parser.parse_args()
    try:
        if args.check:
            readiness(CONFIG)
            return
        if not sys.stdin.isatty():
            raise ValueError('Run this yourself in an interactive terminal. Password input is hidden.')
        password = getpass.getpass('Gmail app password (hidden; spaces are removed): ').replace(' ', '')
        save_password(CONFIG, password)
        del password
        print('Saved SMTP and IMAP passwords to the ignored local .env with owner-only permissions.')
        print('No connection or restart performed. Restart services only when you choose.')
    except Exception:
        # Do not print arbitrary exception details: provider/config data could contain secrets.
        print('Could not save/check local settings. Use an interactive terminal and a regular writable .env file.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
