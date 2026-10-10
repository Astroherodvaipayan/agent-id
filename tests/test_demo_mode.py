from fastapi.testclient import TestClient
from app.api import app
from app import core


def test_demo_mode_blocks_transport_and_uses_current_campaign(monkeypatch, tmp_path):
    monkeypatch.setenv('DEMO_MODE', '1')
    monkeypatch.setenv('OPERATOR_TOKEN', 'demo-local')
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'demo.sqlite3'))
    monkeypatch.setenv('CREATOR_EMAIL', 'creator@example.test')
    monkeypatch.setenv('SMTP_FROM', 'studio@example.test')
    monkeypatch.setenv('BRAND_REPLY_TO', 'studio@example.test')
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'synthetic-test-model')
    monkeypatch.setattr('app.api.suggest_from_reply', lambda idea, body: {'suggested_budget_paise': 2000000, 'rationale': idea + body})
    client = TestClient(app)
    headers = {'Authorization': 'Bearer demo-local'}
    assert client.get('/workspace/config', headers=headers).json()['demo_mode'] is True
    assert client.post('/send', headers=headers, json={'operation_id': 'x', 'amount_paise': 100}).status_code == 403
    assert client.post('/inbox/poll', headers=headers).status_code == 403
    assert client.post('/negotiations/run', headers=headers, json={'negotiation_ids': [], 'operator': 'demo'}).status_code == 403
    draft = core.draft('Autumn launch', 'creator@example.test', 3000000, target_markets=['Mumbai'])
    response = client.post('/demo/suggest', headers=headers, json={'revision': draft['revision'], 'body': 'My quote is INR 28000'})
    assert response.status_code == 200
    assert 'Autumn launch' in response.json()['rationale']
    assert client.post('/demo/suggest', headers=headers, json={'revision': draft['revision'] + 1, 'body': 'test'}).status_code == 400
