"""Load the operator's ignored local settings without replacing process environment."""

from pathlib import Path
import os
from dotenv import dotenv_values


DEFAULT_PATH = Path(__file__).resolve().parents[1] / '.env'
ALLOWED_KEYS = frozenset({
    'AGNTID_MCP_URL', 'AGNTID_ACCESS_TOKEN', 'AGNTID_AGENT_ID', 'AGNTID_USER_ID',
    'AGNTID_TOOL_TOKEN', 'AGNTID_NEGOTIATOR_AGENT_ID', 'AGNTID_REQUIRE_CONTEXTUAL',
    'SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_FROM',
    'SMTP_STARTTLS', 'IMAP_HOST', 'IMAP_PORT', 'IMAP_USERNAME', 'IMAP_PASSWORD',
    'CREATOR_EMAIL', 'CREATOR_EMAILS', 'BRAND_REPLY_TO', 'DATABASE_PATH',
    'GEMINI_API_KEY', 'GEMINI_MODEL', 'OPERATOR_TOKEN', 'MCP_PORT',
    'INITIAL_THREAD_MESSAGE_ID', 'ANONYMOUS_SMTP_FROM', 'ANONYMOUS_REPLY_TO',
    'ANONYMOUS_IDENTITY_REVIEWED', 'WYLD_PROVIDER', 'WYLD_API_KEY',
    'WYLD_SEARCH_URL', 'WYLD_BACKEND_SECRET',
})


def load_local_config(path=DEFAULT_PATH):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return False
    for name, value in dotenv_values(path, interpolate=False).items():
        if name in ALLOWED_KEYS and value is not None:
            os.environ.setdefault(name, value)
    return True
