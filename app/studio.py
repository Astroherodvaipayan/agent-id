"""Campaign Studio planning records. Shortlisting never grants email authority."""
import json
import re
from . import core


def connection():
    c = core.db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS studio_details (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, data_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS creator_discovery (username TEXT PRIMARY KEY, profile_json TEXT NOT NULL, source TEXT NOT NULL, observed_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS studio_shortlist (username TEXT PRIMARY KEY, revision INTEGER NOT NULL, quoted_paise INTEGER, negotiated_paise INTEGER, notes TEXT NOT NULL DEFAULT '');
    ''')
    return c


def record_discovery(result):
    c = connection()
    try:
        for item in result.get('items', []):
            username = str(item.get('username') or '').lower().removeprefix('@')
            if not re.fullmatch(r'[a-z0-9._]{1,30}', username):
                continue
            c.execute('INSERT OR REPLACE INTO creator_discovery(username,profile_json,source) VALUES (?,?,?)', (username, json.dumps({**item, 'username': username}), result['source']))
    finally:
        c.close()


def _campaign(c, revision):
    row = c.execute('SELECT * FROM campaign WHERE id=1').fetchone()
    if not row or row['revision'] != revision:
        raise ValueError('Stale or missing campaign')
    return row


def save_details(revision, details):
    c = connection()
    try:
        c.execute('BEGIN IMMEDIATE')
        _campaign(c, revision)
        clean = {key: str(details.get(key) or '').strip()[:limit] for key, limit in {'name': 120, 'brand_name': 120, 'category': 80, 'target_audience': 600, 'campaign_window': 120, 'notes': 1500}.items()}
        c.execute('INSERT OR REPLACE INTO studio_details(id,revision,data_json) VALUES (1,?,?)', (revision, json.dumps(clean)))
        core.event(c, 'studio_details_saved', {'revision': revision})
        c.execute('COMMIT')
        return clean
    except:
        c.execute('ROLLBACK')
        raise
    finally:
        c.close()


def shortlist(revision, username, quoted_paise=None, negotiated_paise=None, notes='', remove=False):
    username = username.lower().removeprefix('@')
    for value in (quoted_paise, negotiated_paise):
        if value is not None and (type(value) is not int or not 0 <= value <= core.CEILING):
            raise ValueError('Invalid planning price')
    c = connection()
    try:
        c.execute('BEGIN IMMEDIATE')
        _campaign(c, revision)
        if remove:
            c.execute('DELETE FROM studio_shortlist WHERE username=? AND revision=?', (username, revision))
        else:
            if not c.execute('SELECT 1 FROM creator_discovery WHERE username=?', (username,)).fetchone():
                raise ValueError('Run creator search before shortlisting this profile')
            c.execute('INSERT OR REPLACE INTO studio_shortlist(username,revision,quoted_paise,negotiated_paise,notes) VALUES (?,?,?,?,?)', (username, revision, quoted_paise, negotiated_paise, notes[:1500]))
        core.event(c, 'studio_shortlist_updated', {'revision': revision, 'username': username, 'removed': remove, 'purpose': 'planning only; no recipient authorization'})
        c.execute('COMMIT')
    except:
        c.execute('ROLLBACK')
        raise
    finally:
        c.close()


def snapshot():
    c = connection()
    try:
        campaign = c.execute('SELECT revision FROM campaign WHERE id=1').fetchone()
        revision = campaign['revision'] if campaign else 0
        details = c.execute('SELECT data_json FROM studio_details WHERE id=1 AND revision=?', (revision,)).fetchone()
        rows = c.execute('SELECT s.*,d.profile_json,d.source,d.observed_at FROM studio_shortlist s JOIN creator_discovery d ON s.username=d.username WHERE s.revision=? ORDER BY s.username', (revision,)).fetchall()
        creators = [{**dict(row), 'profile': json.loads(row['profile_json'])} for row in rows]
        for creator in creators:
            del creator['profile_json']
        priced = [x for x in creators if x['negotiated_paise'] is not None or x['quoted_paise'] is not None]
        total = sum(x['negotiated_paise'] if x['negotiated_paise'] is not None else x['quoted_paise'] for x in priced)
        return {'details': json.loads(details['data_json']) if details else {}, 'creators': creators, 'planning_total_paise': total if priced else None, 'unpriced_count': len(creators)-len(priced), 'price_source': 'Operator-entered planning figures; not booked spend'}
    finally:
        c.close()
