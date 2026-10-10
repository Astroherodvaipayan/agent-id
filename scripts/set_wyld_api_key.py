#!/usr/bin/env python3
"""User-operated hidden entry for the read-only creator adapter. No network calls."""
import argparse
import getpass
import os
from pathlib import Path
import re
import sys
import tempfile
CONFIG=Path(__file__).resolve().parents[1]/'.env'


def save_key(path,key):
    if not key.strip() or any(c in key for c in '\r\n\x00'):raise ValueError('Invalid local key')
    if path.is_symlink():raise ValueError('Use a regular local settings file')
    lines=path.read_text().splitlines() if path.exists() else []
    pattern=re.compile(r'^\s*(?:export\s+)?(?:WYLD_API_KEY|WYLD_PROVIDER)\s*=')
    lines=[line for line in lines if not pattern.match(line)]
    escaped=key.replace('\\','\\\\').replace('"','\\"')
    lines+=['WYLD_PROVIDER=public','WYLD_API_KEY="'+escaped+'"']
    fd,temp=tempfile.mkstemp(prefix='.email-config-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f:
            f.write('\n'.join(lines)+'\n');f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def main():
    parser=argparse.ArgumentParser(description='Enter a creator API key locally with hidden input.')
    parser.add_argument('--check',action='store_true',help='Print non-secret configuration presence flags only')
    args=parser.parse_args()
    try:
        if args.check:
            if CONFIG.is_symlink():raise ValueError('Unsupported local config')
            from dotenv import dotenv_values
            values=dotenv_values(CONFIG) if CONFIG.exists() else {}
            print('Public creator provider selected:',values.get('WYLD_PROVIDER')=='public')
            print('WYLD_API_KEY configured:',bool(values.get('WYLD_API_KEY')))
            print('Configuration presence only; no live API connection verified.')
            return
        if not sys.stdin.isatty():raise ValueError('Use your own interactive terminal')
        key=getpass.getpass('Creator API key (hidden): ').strip()
        save_key(CONFIG,key);del key
        print('Saved the public read-only adapter settings locally. No API call or restart performed.')
        print('Use a dedicated read-only key if available; rotate any key shared in chat.')
    except Exception:
        print('Local entry/check failed. Use an interactive terminal and a regular writable .env.',file=sys.stderr)
        raise SystemExit(1)

if __name__=='__main__':main()
