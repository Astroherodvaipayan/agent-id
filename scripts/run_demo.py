"""Run the real Campaign Studio workflow with isolated data and mock email transport."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ['DEMO_MODE'] = '1'
os.environ['DATABASE_PATH'] = os.getenv('DEMO_DATABASE_PATH', str(ROOT / 'demo.sqlite3'))
os.environ['OPERATOR_TOKEN'] = 'demo-local'
os.environ['CREATOR_EMAIL'] = 'maya@creator.example'
os.environ['SMTP_FROM'] = 'partnerships@glowkind.example'
os.environ['BRAND_REPLY_TO'] = 'partnerships@glowkind.example'
os.environ.pop('SMTP_HOST', None)
os.environ.pop('AGNTID_MCP_URL', None)

import uvicorn

if __name__ == '__main__':
    port = int(os.getenv('DEMO_PORT', '8765'))
    print(f'Trial portal: http://127.0.0.1:{port}/  |  operator token: demo-local')
    print('Demo data: demo.sqlite3  |  email dispatch blocked')
    uvicorn.run('app.api:app', host='127.0.0.1', port=port)
