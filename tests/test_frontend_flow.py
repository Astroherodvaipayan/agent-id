from fastapi.testclient import TestClient

from app.api import app


def test_guided_home_and_asset(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("OPERATOR_TOKEN", "test-token")
    monkeypatch.setenv("CREATOR_EMAIL", "creator@example.test")
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 200
    assert "What is the campaign idea" in page.text
    assert "The right voices" in page.text
    assert "Send approved proposal" in page.text
    assert "Creator agents above have separate approvals" in page.text
    assert client.get("/assets/wyld-bg-neon-night.webp").status_code == 200
    assert client.get("/workspace/config").status_code == 401
    config = client.get("/workspace/config", headers={"Authorization": "Bearer test-token"})
    assert config.json()["controlled_creator_email"] == "creator@example.test"


def test_model_budget_cannot_raise_brand_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("OPERATOR_TOKEN", "test-token")
    monkeypatch.setenv("CREATOR_EMAIL", "creator@example.test")
    monkeypatch.setattr("app.api.plan_campaign", lambda *_: {"suggested_budget_paise": 4_000_000, "brief": "Draft", "creator_intro": "Hello creator", "risk_flags": [], "rationale": "Estimate"})
    client = TestClient(app)
    result = client.post("/campaign/ai", headers={"Authorization": "Bearer test-token"}, json={"idea": "Launch", "creator": "creator@example.test", "budget_paise": 2_400_000, "target_markets": ["India"]})
    assert result.status_code == 200
    assert result.json()["suggested_budget_paise"] == 2_400_000
    assert client.get("/state", headers={"Authorization": "Bearer test-token"}).json()["campaign"][0]["budget_paise"] == 2_400_000


def test_model_fee_estimate_cannot_shrink_brand_campaign_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("OPERATOR_TOKEN", "test-token")
    monkeypatch.setenv("CREATOR_EMAIL", "creator@example.test")
    monkeypatch.setattr("app.api.plan_campaign", lambda *_: {"suggested_budget_paise": 1, "brief": "Draft", "creator_intro": "Hello creator", "risk_flags": [], "rationale": "Estimate"})
    client = TestClient(app)
    result = client.post("/campaign/ai", headers={"Authorization": "Bearer test-token"}, json={"idea": "Launch", "creator": "creator@example.test", "budget_paise": 4_000_000, "target_markets": ["Mumbai"]})
    assert result.status_code == 200
    assert result.json()["suggested_budget_paise"] == 1
    assert client.get("/state", headers={"Authorization": "Bearer test-token"}).json()["campaign"][0]["budget_paise"] == 4_000_000
