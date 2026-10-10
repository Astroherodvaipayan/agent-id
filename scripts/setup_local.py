#!/usr/bin/env python3
"""User-operated one-command local setup. Never connects to a service."""

import getpass
from pathlib import Path
import sys

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.set_email_password import GMAIL_DEFAULTS, save_password, save_gmail_defaults
from scripts.set_operator_token import save_token
from scripts.set_wyld_api_key import save_key

CONFIG = Path(__file__).resolve().parents[1] / '.env'


def flags(path):
    if path.is_symlink():
        raise ValueError('Unsupported local config')
    return dotenv_values(path, interpolate=False) if path.exists() else {}


def configure(path, hidden_input=getpass.getpass, output=print):
    if path.is_symlink():
        raise ValueError('Unsupported local config')
    values = flags(path)
    if not values.get('OPERATOR_TOKEN'):
        save_token(path, hidden_input('Choose or enter a private dashboard password (hidden): '))
        output('Operator token saved.')
    else:
        output('Operator token already configured; kept existing value.')

    values = flags(path)
    if not values.get('WYLD_API_KEY'):
        save_key(path, hidden_input('Wild Samaj API key (hidden): '))
        output('Wild Samaj key saved; public provider selected.')
    elif values.get('WYLD_PROVIDER') != 'public':
        save_key(path, values['WYLD_API_KEY'])
        output('Existing Wild Samaj key kept; public provider selected.')
    else:
        output('Wild Samaj key already configured; kept existing value.')

    values = flags(path)
    if not (values.get('SMTP_PASSWORD') and values.get('IMAP_PASSWORD')):
        save_password(path, hidden_input('Gmail app password (hidden; spaces removed): ').replace(' ', ''))
        output('Gmail app password and connection defaults saved.')
    else:
        output('Email passwords already configured; kept existing values.')

    save_gmail_defaults(path)

    values = flags(path)
    output('Setup presence flags:')
    output('  Operator token: ' + ('ready' if values.get('OPERATOR_TOKEN') else 'missing'))
    output('  Wild Samaj public key: ' + ('ready' if values.get('WYLD_PROVIDER') == 'public' and values.get('WYLD_API_KEY') else 'missing'))
    output('  Gmail password: ' + ('ready' if values.get('SMTP_PASSWORD') and values.get('IMAP_PASSWORD') else 'missing'))
    output('  Gmail connection fields: ' + ('ready' if all(values.get(key) for key in GMAIL_DEFAULTS) else 'incomplete'))
    output('No connection was tested. Restart the dashboard to load newly saved settings.')


def main():
    try:
        if not sys.stdin.isatty():
            raise ValueError('Interactive terminal required')
        configure(CONFIG)
    except Exception:
        print('Local setup stopped. Use your own interactive terminal and a regular writable .env.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
