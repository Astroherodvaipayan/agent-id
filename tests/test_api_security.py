from fastapi.testclient import TestClient
from app.api import app

def test_operator_auth_and_cross_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("CREATOR_EMAIL", "creator@example.test")
    c = TestClient(app)
    assert c.get("/state").status_code == 503
    monkeypatch.setenv("OPERATOR_TOKEN", "test-token")
    assert c.get("/state").status_code == 401
    h = {"Authorization": "Bearer test-token"}
    assert c.get("/state", headers=h).status_code == 200
    bad = {**h, "Origin": "https://evil.example"}
    assert c.post("/campaign", json={"idea": "x", "creator": "creator@example.test", "budget_paise": 2400000}, headers=bad).status_code == 403

def test_model_route_explicitly_unconfigured(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("OPERATOR_TOKEN", "test-token")
    monkeypatch.setenv("CREATOR_EMAIL", "creator@example.test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    c = TestClient(app)
    h = {"Authorization": "Bearer test-token"}
    assert c.post("/campaign/ai", json={"idea": "idea", "creator": "creator@example.test", "budget_paise": 2400000, "target_markets": ["India"]}, headers=h).status_code == 503
