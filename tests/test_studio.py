import pytest
from app import core, studio

@pytest.fixture
def campaign(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'studio.sqlite3'))
    monkeypatch.setenv('CREATOR_EMAIL', 'creator@example.test')
    return core.draft('Launch', 'creator@example.test', 2400000, target_markets=['India'])

def test_shortlist_uses_search_evidence_and_missing_price(campaign):
    rev = campaign['revision']
    with pytest.raises(ValueError, match='search'):
        studio.shortlist(rev, 'unknown')
    studio.record_discovery({'source':'verified-local-search','items':[{'username':'creator','full_name':'Creator'}]})
    studio.shortlist(rev, 'creator')
    snapshot = studio.snapshot()
    assert snapshot['planning_total_paise'] is None
    assert snapshot['unpriced_count'] == 1
    assert snapshot['creators'][0]['source'] == 'verified-local-search'
    studio.shortlist(rev, 'creator', quoted_paise=2000000, negotiated_paise=1800000)
    assert studio.snapshot()['planning_total_paise'] == 1800000
    c = core.db()
    try:
        assert c.execute('SELECT count(*) FROM approval').fetchone()[0] == 0
    finally:
        c.close()

def test_revision_prevents_stale_studio_changes(campaign):
    rev = campaign['revision']
    studio.save_details(rev, {'name':'Original'})
    newer = core.draft('Revised', 'creator@example.test', 2400000, target_markets=['India'])
    assert newer['revision'] != rev
    assert studio.snapshot()['details'] == {}
    with pytest.raises(ValueError, match='Stale'):
        studio.save_details(rev, {'name':'Stale'})
