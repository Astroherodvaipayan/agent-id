#!/usr/bin/env python3
"""User-operated hidden entry for an existing operator token. No network calls."""

import argparse
import getpass
import os
from pathlib import Path
import re
import sys
import tempfile

CONFIG = Path(__file__).resolve().parents[1] / '.env'


def save_token(path, token):
    if not token or any(c in token for c in '\r\n\x00'):
        raise ValueError('Invalid token')
    if path.is_symlink():
        raise ValueError('Unsupported local config')
    lines = path.read_text().splitlines() if path.exists() else []
    pattern = re.compile(r'^\s*(?:export\s+)?OPERATOR_TOKEN\s*=')
    lines = [line for line in lines if not pattern.match(line)]
    escaped = token.replace('\\', '\\\\').replace('"', '\\"')
    lines.append('OPERATOR_TOKEN="' + escaped + '"')
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


def main():
    parser = argparse.ArgumentParser(description='Enter your existing operator token locally with hidden input.')
    parser.add_argument('--check', action='store_true', help='Print a presence flag only')
    args = parser.parse_args()
    try:
        if args.check:
            if CONFIG.is_symlink():
                raise ValueError('Unsupported local config')
            from dotenv import dotenv_values
            values = dotenv_values(CONFIG, interpolate=False) if CONFIG.exists() else {}
            print('OPERATOR_TOKEN configured:', bool(values.get('OPERATOR_TOKEN')))
            return
        if not sys.stdin.isatty():
            raise ValueError('Interactive terminal required')
        token = getpass.getpass('Choose or enter a private dashboard password (hidden): ')
        save_token(CONFIG, token)
        del token
        print('Saved the operator token to the ignored local config. Restart the dashboard to use it.')
    except Exception:
        print('Local entry/check failed. Use an interactive terminal and a regular writable .env.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
