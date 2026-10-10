import sqlite3
from app import core

def test_old_local_database_is_migrated_without_losing_campaign(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE campaign (id INTEGER PRIMARY KEY, idea TEXT NOT NULL, creator TEXT NOT NULL, brief TEXT NOT NULL, budget_paise INTEGER NOT NULL, evidence TEXT NOT NULL, revision INTEGER NOT NULL)")
    c.execute("INSERT INTO campaign VALUES (1,'Legacy idea','creator@example.test','Brief',2400000,'Synthetic',1)")
    c.commit(); c.close()
    monkeypatch.setenv("DATABASE_PATH", str(path))
    upgraded = core.db()
    assert upgraded.execute("SELECT idea,target_markets FROM campaign WHERE id=1").fetchone()["idea"] == "Legacy idea"
    assert upgraded.execute("SELECT status FROM guardrail_review WHERE id=1").fetchone()[0] == "pending"
    upgraded.close()
