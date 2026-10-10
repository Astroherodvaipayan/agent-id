"""Creator-scoped approval and durable shared campaign budget reservations."""
import json
import os
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from . import core


def db():
    c = core.db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS negotiations (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, creator_handle TEXT NOT NULL, recipient TEXT NOT NULL, phase TEXT NOT NULL DEFAULT 'anonymous', contact_evidence TEXT NOT NULL, created_by TEXT NOT NULL, reveal_approver TEXT, reveal_evidence TEXT, UNIQUE(revision,recipient));
    CREATE TABLE IF NOT EXISTS negotiation_approval (negotiation_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE, amount_paise INTEGER NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, approver TEXT NOT NULL, expires_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS negotiation_outbox (operation_id TEXT PRIMARY KEY, negotiation_id TEXT NOT NULL UNIQUE, amount_paise INTEGER NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, message_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS negotiation_runs (id TEXT PRIMARY KEY, negotiation_id TEXT NOT NULL, operation_id TEXT NOT NULL, task_id TEXT, delegation_id TEXT, status TEXT NOT NULL, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS negotiation_reporting (id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, event_reference TEXT NOT NULL, outcome TEXT NOT NULL, operator TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS negotiation_cancellations (negotiation_id TEXT PRIMARY KEY, operator TEXT NOT NULL, evidence TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS negotiation_confirmations (negotiation_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, operation_id TEXT NOT NULL, operator TEXT NOT NULL, agreement_reference TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS negotiation_replies (uid TEXT PRIMARY KEY, negotiation_id TEXT NOT NULL, sender TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL, thread_match INTEGER NOT NULL DEFAULT 0, evidence TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    # Additive columns and one-time unique-slot migration preserve existing outboxes.
    columns={r['name'] for r in c.execute('PRAGMA table_info(negotiations)')}
    for name,spec in {'active_round':'INTEGER NOT NULL DEFAULT 1','max_rounds':'INTEGER NOT NULL DEFAULT 3','deadline':'TEXT','termination':'TEXT'}.items():
        if name not in columns:c.execute('ALTER TABLE negotiations ADD COLUMN '+name+' '+spec)
    c.execute("UPDATE negotiations SET deadline=? WHERE deadline IS NULL",((datetime.now(timezone.utc)+timedelta(hours=4)).isoformat(),))
    if 'round' not in {r['name'] for r in c.execute('PRAGMA table_info(negotiation_outbox)')}:
        c.executescript("""
        BEGIN IMMEDIATE;
        ALTER TABLE negotiation_outbox RENAME TO negotiation_outbox_legacy;
        CREATE TABLE negotiation_outbox (operation_id TEXT PRIMARY KEY, negotiation_id TEXT NOT NULL, amount_paise INTEGER NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, message_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, round INTEGER NOT NULL DEFAULT 1, UNIQUE(negotiation_id,round));
        INSERT INTO negotiation_outbox(operation_id,negotiation_id,amount_paise,payload_hash,payload_json,message_id,status,detail,created_at) SELECT operation_id,negotiation_id,amount_paise,payload_hash,payload_json,message_id,status,detail,created_at FROM negotiation_outbox_legacy;
        DROP TABLE negotiation_outbox_legacy;
        COMMIT;
        """)
    if 'operation_id' not in {r['name'] for r in c.execute('PRAGMA table_info(negotiation_replies)')}:
        c.execute('ALTER TABLE negotiation_replies ADD COLUMN operation_id TEXT')
    c.executescript("""CREATE TABLE IF NOT EXISTS negotiation_rounds (negotiation_id TEXT NOT NULL, round INTEGER NOT NULL, reply_uid TEXT NOT NULL UNIQUE, previous_operation TEXT NOT NULL, operator TEXT NOT NULL, supersession_evidence TEXT NOT NULL, suggestion_json TEXT NOT NULL, PRIMARY KEY(negotiation_id,round));""")
    return c


def allowlist():
    entries = os.getenv('CREATOR_EMAILS', os.getenv('CREATOR_EMAIL', '')).split(',')
    return {x.strip().lower() for x in entries if x.strip()}


def create(revision, creator_handle, recipient, operator, evidence):
    recipient = recipient.strip().lower()
    if recipient not in allowlist() or parseaddr(recipient)[1] != recipient or '\n' in recipient or '\r' in recipient:
        raise ValueError('Recipient outside the configured creator allowlist')
    if not operator.strip() or not evidence.strip():
        raise ValueError('Verified contact evidence and operator required')
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        campaign = c.execute('SELECT revision FROM campaign WHERE id=1').fetchone()
        if not campaign or campaign['revision'] != revision:
            raise ValueError('Stale campaign revision')
        old = c.execute('SELECT id FROM negotiations WHERE revision=? AND recipient=?', (revision, recipient)).fetchone()
        if old:
            c.execute('COMMIT')
            return old['id']
        identity = secrets.token_hex(12)
        c.execute('INSERT INTO negotiations(id,revision,creator_handle,recipient,contact_evidence,created_by) VALUES (?,?,?,?,?,?)', (identity,revision,creator_handle[:80],recipient,evidence[:2000],operator[:120]))
        core.event(c,'creator_negotiation_created',{'negotiation_id':identity,'revision':revision,'phase':'anonymous','contact_evidence':evidence[:2000]})
        c.execute('COMMIT')
        return identity
    except:
        c.execute('ROLLBACK')
        raise
    finally:
        c.close()


def reveal(identity, revision, operator, evidence):
    if not operator.strip() or not evidence.strip():
        raise ValueError('Explicit brand reveal approval and evidence required')
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        n, campaign = current(c, identity)
        if n['revision'] != revision:
            raise ValueError('Stale reveal approval')
        if c.execute('SELECT 1 FROM negotiation_outbox WHERE negotiation_id=? AND round=?', (identity,n['active_round'])).fetchone():
            raise ValueError('Active proposal already dispatched or reserved; prepare a verified reply round first')
        c.execute("UPDATE negotiations SET phase='revealed',reveal_approver=?,reveal_evidence=? WHERE id=?", (operator,evidence[:2000],identity))
        c.execute('DELETE FROM negotiation_approval WHERE negotiation_id=?',(identity,))
        core.event(c,'brand_reveal_approved',{'negotiation_id':identity,'operator':operator,'evidence':evidence[:2000]})
        c.execute('COMMIT')
    except:
        c.execute('ROLLBACK')
        raise
    finally:
        c.close()


def current(c, identity):
    n = c.execute('SELECT * FROM negotiations WHERE id=?',(identity,)).fetchone()
    campaign = c.execute('SELECT * FROM campaign WHERE id=1').fetchone()
    if not n or not campaign or n['revision'] != campaign['revision']:
        raise ValueError('Missing negotiation or stale campaign brief')
    if c.execute('SELECT 1 FROM negotiation_cancellations WHERE negotiation_id=?',(identity,)).fetchone():
        raise ValueError('Creator lane cancelled')
    if n['termination']:
        raise ValueError('Creator negotiation terminated: '+n['termination'])
    if n['deadline']<=datetime.now(timezone.utc).isoformat():
        raise ValueError('Creator negotiation deadline reached')
    if n['recipient'] not in allowlist():
        raise ValueError('Recipient no longer allowed')
    review = c.execute('SELECT revision,status FROM guardrail_review WHERE id=1').fetchone()
    if not review or review['revision'] != campaign['revision'] or review['status'] != 'approved':
        raise ValueError('Campaign brief needs operator review')
    return n, campaign


def payload(c, identity, amount):
    n,campaign = current(c,identity)
    if type(amount) is not int or not 0 <= amount <= min(core.CEILING,campaign['budget_paise']):
        raise ValueError('Proposal amount exceeds campaign budget or backend ceiling')
    if n['phase'] == 'anonymous':
        sender,reply = os.getenv('ANONYMOUS_SMTP_FROM',''),os.getenv('ANONYMOUS_REPLY_TO','')
        if not sender or not reply or os.getenv('ANONYMOUS_IDENTITY_REVIEWED','').lower() != 'true':
            raise ValueError('Anonymous stage unavailable: separately reviewed neutral sender and reply-to required')
        # Prevent obvious brand-address leakage. Provider rewrite must still be checked independently.
        brand_domains={parseaddr(os.getenv(key,''))[1].split('@')[-1].lower() for key in ('SMTP_FROM','BRAND_REPLY_TO') if os.getenv(key)}
        if any(parseaddr(address)[1].split('@')[-1].lower() in brand_domains for address in (sender,reply)):
            raise ValueError('Anonymous stage unavailable: sender or reply-to identifies the brand domain')
    else:
        if not n['reveal_approver']:
            raise ValueError('Brand reveal lacks explicit approval')
        sender,reply=os.getenv('SMTP_FROM',''),os.getenv('BRAND_REPLY_TO','')
    for address in (sender,reply):
        if not address or parseaddr(address)[1] != address or any(x in address for x in ('\r','\n')):
            raise ValueError('Configure a valid sender and reply-to')
    previous=c.execute('SELECT o.message_id FROM negotiation_rounds r JOIN negotiation_outbox o ON r.previous_operation=o.operation_id WHERE r.negotiation_id=? AND r.round=?',(identity,n['active_round'])).fetchone()
    thread=previous['message_id'] if previous else None
    text=core.proposal_text('',amount)
    if thread:text='This revised nonbinding proposal replaces our earlier nonbinding proposal '+thread+'.\n\n'+text
    return {'previous_message_id':thread,'recipient':n['recipient'],'from':sender,'reply_to':reply,'subject':'Nonbinding collaboration proposal','body':text,'amount_paise':amount,'package':core.PACKAGE,'negotiation_id':identity,'phase':n['phase'],'round':n['active_round'],'brief_revision':campaign['revision'],'brief_hash':core.payload_hash({'idea':campaign['idea'],'brief':campaign['brief'],'markets':campaign['target_markets'],'budget':campaign['budget_paise']})}


def preview(identity,amount):
    c=db()
    try:
        p=payload(c,identity,amount)
        return {**p,'preview_hash':core.payload_hash(p)}
    finally:
        c.close()


def approve(identity,amount,digest,operator):
    if not operator.strip():
        raise ValueError('Operator required')
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE')
        p=payload(c,identity,amount)
        if not digest or core.payload_hash(p) != digest:
            raise ValueError('Stale exact proposal preview')
        n,_=current(c,identity)
        if c.execute('SELECT 1 FROM negotiation_outbox WHERE negotiation_id=? AND round=?',(identity,n['active_round'])).fetchone():
            raise ValueError('Creator proposal slot already used')
        old=c.execute('SELECT * FROM negotiation_approval WHERE negotiation_id=?',(identity,)).fetchone()
        if old and old['payload_hash']==digest and old['expires_at']>datetime.now(timezone.utc).isoformat() and not c.execute("SELECT 1 FROM negotiation_runs WHERE operation_id=? AND status IN ('denied','blocked')",(old['operation_id'],)).fetchone():
            c.execute('COMMIT');return dict(old)
        operation=secrets.token_hex(16)
        expires=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
        c.execute('INSERT OR REPLACE INTO negotiation_approval VALUES (?,?,?,?,?,?,?)',(identity,operation,amount,json.dumps(p,sort_keys=True),digest,operator,expires))
        core.event(c,'creator_proposal_approved',{'negotiation_id':identity,'operation_id':operation,'amount_paise':amount,'preview_hash':digest,'operator':operator})
        c.execute('COMMIT')
        return dict(c.execute('SELECT * FROM negotiation_approval WHERE negotiation_id=?',(identity,)).fetchone())
    except:
        c.execute('ROLLBACK');raise
    finally:
        c.close()


def approved_request(identity):
    c=db()
    try:
        row=c.execute('SELECT * FROM negotiation_approval WHERE negotiation_id=?',(identity,)).fetchone()
        if not row or row['expires_at']<=datetime.now(timezone.utc).isoformat():
            raise ValueError('Missing or expired proposal approval')
        fresh=payload(c,identity,row['amount_paise'])
        if core.payload_hash(fresh)!=row['payload_hash']:
            raise ValueError('Proposal approval no longer matches brief, recipient or phase')
        return dict(row)
    finally:c.close()


def reserve(identity,operation,amount):
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM negotiation_outbox WHERE operation_id=?',(operation,)).fetchone()
        if old:
            if old['negotiation_id']!=identity or old['amount_paise']!=amount:
                raise ValueError('Operation arguments conflict')
            c.execute('COMMIT');return dict(old),False
        n,_=current(c,identity)
        if c.execute('SELECT 1 FROM negotiation_outbox WHERE negotiation_id=? AND round=?',(identity,n['active_round'])).fetchone():
            raise ValueError('Creator proposal slot already used')
        n,campaign=current(c,identity)
        approval=c.execute('SELECT * FROM negotiation_approval WHERE negotiation_id=? AND operation_id=?',(identity,operation)).fetchone()
        if not approval or approval['amount_paise']!=amount or approval['expires_at']<=datetime.now(timezone.utc).isoformat():
            raise ValueError('Approval mismatch or expired')
        p=payload(c,identity,amount)
        digest=core.payload_hash(p)
        if digest!=approval['payload_hash']:
            raise ValueError('Approved terms changed')
        total=c.execute("SELECT COALESCE(SUM(amount_paise),0) FROM negotiation_outbox WHERE status NOT IN ('not_sent_reconciled','cancelled_before_dispatch','superseded_reconciled')").fetchone()[0]
        legacy=c.execute("SELECT COALESCE(SUM(amount_paise),0) FROM outbox WHERE status NOT IN ('not_sent_reconciled','cancelled_before_dispatch','superseded_reconciled')").fetchone()[0]
        previous=c.execute('SELECT * FROM negotiation_rounds WHERE negotiation_id=? AND round=?',(identity,n['active_round'])).fetchone()
        release=0
        if previous:
            prior=c.execute('SELECT * FROM negotiation_outbox WHERE operation_id=?',(previous['previous_operation'],)).fetchone()
            if not prior or prior['status']!='inbox_received' or not previous['supersession_evidence']:
                raise ValueError('Prior proposal supersession must be verified before replacement')
            release=prior['amount_paise']
        if total+legacy-release+amount>campaign['budget_paise']:
            raise ValueError('Shared campaign budget exhausted')
        message_id=make_msgid(domain=p['from'].split('@')[-1])
        if previous:c.execute("UPDATE negotiation_outbox SET status='superseded_reconciled',detail=? WHERE operation_id=?",(previous['supersession_evidence'],previous['previous_operation']))
        c.execute('INSERT INTO negotiation_outbox(operation_id,negotiation_id,amount_paise,payload_hash,payload_json,message_id,status,round) VALUES (?,?,?,?,?,?,?,?)',(operation,identity,amount,digest,json.dumps(p,sort_keys=True),message_id,'reserved',n['active_round']))
        core.event(c,'shared_budget_reserved',{'negotiation_id':identity,'operation_id':operation,'amount_paise':amount,'reserved_total_paise':total+legacy-release+amount,'enforcement':'backend atomic ledger; not AgntID aggregate policy'})
        c.execute('COMMIT')
        return dict(c.execute('SELECT * FROM negotiation_outbox WHERE operation_id=?',(operation,)).fetchone()),True
    except:
        c.execute('ROLLBACK');raise
    finally:c.close()


RELEASED_STATES=('not_sent_reconciled','cancelled_before_dispatch','superseded_reconciled')


def _financial_invariant(c):
    campaign=c.execute('SELECT budget_paise FROM campaign WHERE id=1').fetchone()
    total=c.execute("SELECT COALESCE(SUM(amount_paise),0) FROM negotiation_outbox WHERE status NOT IN ('not_sent_reconciled','cancelled_before_dispatch','superseded_reconciled')").fetchone()[0]
    legacy=c.execute("SELECT COALESCE(SUM(amount_paise),0) FROM outbox WHERE status!='not_sent_reconciled'").fetchone()[0]
    if not campaign or total+legacy>campaign['budget_paise']:
        raise ValueError('Shared campaign budget invariant violated')


def _current_operation(c,out):
    lane=c.execute('SELECT * FROM negotiations WHERE id=?',(out['negotiation_id'],)).fetchone()
    campaign=c.execute('SELECT revision FROM campaign WHERE id=1').fetchone()
    if not lane or not campaign or lane['revision']!=campaign['revision'] or out['round']!=lane['active_round']:
        raise ValueError('Operation is not the current creator round')


def status(operation,state,detail):
    if state not in ('reserved','dispatching','unknown','accepted_by_smtp','accepted_reconciled','inbox_received'):
        raise ValueError('Unsupported provider delivery state')
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE')
        out=c.execute('SELECT * FROM negotiation_outbox WHERE operation_id=?',(operation,)).fetchone()
        if not out:raise ValueError('Unknown operation')
        if out['status'] in RELEASED_STATES:raise ValueError('Released or superseded proposal is terminal')
        _current_operation(c,out)
        # A late provider completion cannot erase stronger manually verified receipt evidence.
        if out['status'] in ('inbox_received','accepted_reconciled') and state in ('unknown','accepted_by_smtp','dispatching','reserved'):
            core.event(c,'creator_delivery_evidence_appended',{'operation_id':operation,'observed_status':state,'detail':detail,'financial_state':out['status']})
        else:
            c.execute('UPDATE negotiation_outbox SET status=?,detail=? WHERE operation_id=?',(state,detail,operation))
            core.event(c,'creator_delivery_state',{'operation_id':operation,'status':state,'detail':detail})
        _financial_invariant(c)
        c.execute('COMMIT')
    except:
        if c.in_transaction:c.execute('ROLLBACK')
        raise
    finally:c.close()


def send_creator_proposal(negotiation_id,operation_id,amount_paise):
    record,fresh=reserve(negotiation_id,operation_id,amount_paise)
    if not fresh:return {'status':record['status'],'message_id':record['message_id'],'duplicate':True}
    # Atomic dispatch claim prevents cancellation releasing funds during a send.
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE')
        changed=c.execute("UPDATE negotiation_outbox SET status='dispatching' WHERE operation_id=? AND status='reserved'",(operation_id,)).rowcount
        c.execute('COMMIT')
        if not changed:return {'status':'cancelled_before_dispatch','duplicate':True}
    finally:c.close()
    p=json.loads(record['payload_json']);msg=EmailMessage()
    for key,value in {'From':p['from'],'To':p['recipient'],'Reply-To':p['reply_to'],'Subject':p['subject'],'Message-ID':record['message_id'],'X-Agent-Operation-ID':operation_id}.items():msg[key]=value
    if p.get('previous_message_id'):
        msg['In-Reply-To']=p['previous_message_id'];msg['References']=p['previous_message_id']
    msg.set_content(p['body'])
    try:
        with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=20) as smtp:
            smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
            if os.getenv('SMTP_USERNAME'):smtp.login(os.environ['SMTP_USERNAME'],os.environ['SMTP_PASSWORD'])
            smtp.send_message(msg,from_addr=p['from'],to_addrs=[p['recipient']])
        status(operation_id,'accepted_by_smtp','Provider acceptance; recipient inbox receipt unverified')
        return {'status':'accepted_by_smtp','message_id':record['message_id']}
    except Exception as exc:
        status(operation_id,'unknown',type(exc).__name__+': provider reconciliation required; no blind retry')
        raise


def snapshot():
    c=db()
    try:
        tables=('negotiations','negotiation_approval','negotiation_outbox','negotiation_runs','negotiation_reporting','negotiation_replies','negotiation_cancellations','negotiation_confirmations','negotiation_rounds')
        result={t:[dict(r) for r in c.execute('SELECT * FROM '+t)] for t in tables}
        # Frozen payload contents are private operator data; no credentials are stored.
        result['reserved_paise']=c.execute("SELECT COALESCE(SUM(amount_paise),0) FROM negotiation_outbox WHERE status NOT IN ('not_sent_reconciled','cancelled_before_dispatch','superseded_reconciled')").fetchone()[0]
        result['anonymous_available']=all(os.getenv(k) for k in ('ANONYMOUS_SMTP_FROM','ANONYMOUS_REPLY_TO')) and os.getenv('ANONYMOUS_IDENTITY_REVIEWED','').lower()=='true'
        return result
    finally:c.close()


def cancel(identity,operator,evidence):
    if not operator.strip() or not evidence.strip():raise ValueError('Cancellation evidence and operator required')
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM negotiations WHERE id=?',(identity,)).fetchone():raise ValueError('Unknown creator lane')
        c.execute('INSERT OR REPLACE INTO negotiation_cancellations VALUES (?,?,?)',(identity,operator,evidence))
        c.execute("UPDATE negotiation_outbox SET status='cancelled_before_dispatch',detail='Operator cancelled before dispatch' WHERE negotiation_id=? AND status='reserved'",(identity,))
        c.execute('DELETE FROM negotiation_approval WHERE negotiation_id=?',(identity,))
        core.event(c,'creator_lane_cancelled',{'negotiation_id':identity,'operator':operator,'evidence':evidence,'reservation_release':'only reserved before dispatch; uncertain sends retain budget'})
        c.execute('COMMIT')
    except:c.execute('ROLLBACK');raise
    finally:c.close()


def reconcile(operation,outcome,operator,evidence):
    if outcome not in ('not_sent','accepted','inbox_received') or not operator.strip() or not evidence.strip():raise ValueError('Verified reconciliation outcome, operator and provider evidence required')
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE')
        out=c.execute('SELECT * FROM negotiation_outbox WHERE operation_id=?',(operation,)).fetchone()
        if not out:raise ValueError('No dispatched operation to reconcile')
        if out['status'] in RELEASED_STATES:raise ValueError('Released or superseded proposal is terminal')
        _current_operation(c,out)
        if out['status']=='reserved':raise ValueError('Proposal has not been dispatched')
        if outcome=='not_sent' and out['status'] != 'unknown':raise ValueError('Only an uncertain completed send can be reconciled as not sent; active dispatch retains budget')
        if out['status']=='inbox_received' and outcome!='inbox_received':raise ValueError('Verified inbox receipt cannot be downgraded')
        state={'not_sent':'not_sent_reconciled','accepted':'accepted_reconciled','inbox_received':'inbox_received'}[outcome]
        c.execute('UPDATE negotiation_outbox SET status=?,detail=? WHERE operation_id=?',(state,'Operator '+operator+': '+evidence,operation))
        core.event(c,'creator_send_reconciled',{'operation_id':operation,'outcome':outcome,'operator':operator,'evidence':evidence})
        _financial_invariant(c)
        c.execute('COMMIT')
    except:c.execute('ROLLBACK');raise
    finally:c.close()


def ingest_reply(uid,sender,body,references):
    """Untrusted mail is stored first and quarantined; headers never approve actions."""
    import re
    sender=sender.lower().strip()
    refs=set(re.findall(r'<[^<>\s]+>',references))
    c=db()
    try:
        old=c.execute('SELECT * FROM negotiation_replies WHERE uid=?',(uid,)).fetchone()
        if old and old['state']!='received':return {'duplicate':True,'negotiation_id':old['negotiation_id']}
        if old:
            identity=old['negotiation_id']
        else:
            matches=[r for r in c.execute('SELECT o.message_id,o.operation_id,n.id,n.recipient FROM negotiation_outbox o JOIN negotiations n ON o.negotiation_id=n.id') if r['message_id'] in refs and r['recipient']==sender and sender in allowlist()]
            if len(matches)!=1:return {'duplicate':False,'routed':False}
            identity=matches[0]['id']
            c.execute("INSERT INTO negotiation_replies(uid,negotiation_id,sender,body,state,thread_match,operation_id) VALUES (?,?,?,?,'received',1,?)",(uid,identity,sender,body[:20000],matches[0]['operation_id']))
        # A crash after INSERT is resumed using the stored event, never replayed as instructions.
        c.execute('BEGIN IMMEDIATE')
        changed=c.execute("UPDATE negotiation_replies SET state='quarantined' WHERE uid=? AND state='received'",(uid,)).rowcount
        if not changed:
            c.execute('COMMIT');return {'duplicate':True,'negotiation_id':identity}
        core.event(c,'creator_reply_quarantined',{'uid':uid,'negotiation_id':identity,'authority':'none; verify provider receipt manually'})
        c.execute('COMMIT')
        return {'duplicate':False,'routed':True,'negotiation_id':identity,'state':'quarantined'}
    finally:c.close()


def verify_reply(uid,operator,evidence):
    if not operator.strip() or not evidence.strip():raise ValueError('Operator and provider receipt evidence required')
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM negotiation_replies WHERE uid=?',(uid,)).fetchone()
        if not row or not row['thread_match'] or row['state']=='received':raise ValueError('Reply not yet durably routed')
        if row['state']=='complete':c.execute('COMMIT');return {'duplicate':True}
        c.execute("UPDATE negotiation_replies SET state='complete',evidence=? WHERE uid=?",(operator+': '+evidence,uid))
        core.event(c,'creator_reply_verified',{'uid':uid,'negotiation_id':row['negotiation_id'],'operator':operator,'evidence':evidence,'authority':'reply data only; no automatic approval'})
        c.execute('COMMIT');return {'duplicate':False}
    except:c.execute('ROLLBACK');raise
    finally:c.close()


def confirm(identity,revision,operation,operator,agreement_reference):
    """Record a human-verified external agreement. No binding action is automated."""
    if not operator.strip() or not agreement_reference.strip():raise ValueError('Human approval and external agreement reference required')
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE')
        n,campaign=current(c,identity)
        out=c.execute('SELECT * FROM negotiation_outbox WHERE negotiation_id=? AND operation_id=?',(identity,operation)).fetchone()
        if revision!=campaign['revision'] or n['phase']!='revealed' or not out or out['round']!=n['active_round'] or out['status']!='inbox_received':raise ValueError('Current revealed brief and verified inbox receipt required')
        if not c.execute("SELECT 1 FROM negotiation_replies WHERE negotiation_id=? AND operation_id=? AND state='complete'",(identity,operation)).fetchone():raise ValueError('Verified creator reply required')
        c.execute('INSERT OR REPLACE INTO negotiation_confirmations(negotiation_id,revision,operation_id,operator,agreement_reference) VALUES (?,?,?,?,?)',(identity,revision,operation,operator,agreement_reference))
        c.execute("UPDATE negotiations SET termination='human_confirmed' WHERE id=?",(identity,))
        core.event(c,'external_agreement_human_verified',{'negotiation_id':identity,'operation_id':operation,'operator':operator,'agreement_reference':agreement_reference,'binding_action':'performed externally by human, not agent'})
        c.execute('COMMIT')
    except:c.execute('ROLLBACK');raise
    finally:c.close()


def prepare_round(identity,reply_uid,operator,supersession_evidence,model=None):
    from .planner import suggest_from_reply
    if not operator.strip() or not supersession_evidence.strip():raise ValueError('Operator and verified prior-proposal supersession evidence required')
    c=db()
    def validate():
        lane,campaign=current(c,identity)
        if lane['active_round']>=lane['max_rounds']:raise ValueError('Maximum negotiation rounds reached')
        if c.execute("SELECT 1 FROM negotiation_outbox WHERE status IN ('unknown','dispatching','reserved')").fetchone():raise ValueError('Uncertain or active campaign send blocks round changes')
        prior=c.execute('SELECT * FROM negotiation_outbox WHERE negotiation_id=? AND round=?',(identity,lane['active_round'])).fetchone()
        reply=c.execute('SELECT * FROM negotiation_replies WHERE uid=?',(reply_uid,)).fetchone()
        if not prior or prior['status']!='inbox_received' or not reply or reply['negotiation_id']!=identity or reply['operation_id']!=prior['operation_id'] or reply['state']!='complete':raise ValueError('New verified reply and inbox receipt for the current proposal required')
        if c.execute('SELECT 1 FROM negotiation_rounds WHERE reply_uid=?',(reply_uid,)).fetchone():raise ValueError('Reply already used for a round')
        return lane,campaign,prior,reply
    try:
        lane,campaign,prior,reply=validate()
        baseline=lane['active_round']
        # Model sees stored verified evidence; it cannot authorize tool calls or edit scope.
        suggestion=(model or suggest_from_reply)(campaign['idea'],reply['body'])
        amount=suggestion.get('suggested_budget_paise')
        if type(amount) is not int or not 0<=amount<=min(core.CEILING,campaign['budget_paise']):raise ValueError('Suggested amount outside campaign bounds')
        c.execute('BEGIN IMMEDIATE')
        lane,campaign,prior,reply=validate()
        if lane['active_round']!=baseline:raise ValueError('Round changed while model drafted suggestion')
        number=baseline+1
        clean={'suggested_budget_paise':amount,'rationale':str(suggestion.get('rationale',''))[:2000],'counteroffer_intro':str(suggestion.get('counteroffer_intro',''))[:600],'risk_flags':suggestion.get('risk_flags',[])[:20],'requires_operator_approval':True,'outbound_wording':'backend fixed template; suggestion text never inserted'}
        c.execute('INSERT INTO negotiation_rounds VALUES (?,?,?,?,?,?,?)',(identity,number,reply_uid,prior['operation_id'],operator,supersession_evidence,json.dumps(clean)))
        c.execute('UPDATE negotiations SET active_round=? WHERE id=?',(number,identity))
        c.execute('DELETE FROM negotiation_approval WHERE negotiation_id=?',(identity,))
        core.event(c,'negotiation_round_prepared',{'negotiation_id':identity,'round':number,'reply_uid':reply_uid,'operator':operator,'supersession_evidence':supersession_evidence,'approval':'required; not automatic'})
        c.execute('COMMIT')
        return {'round':number,'suggestion':clean,'budget_release':'none until atomic replacement reservation'}
    except:
        if c.in_transaction:c.execute('ROLLBACK')
        raise
    finally:c.close()


def terminate(identity,reason,operator,evidence):
    if reason not in ('creator_declined','operator_stopped') or not operator.strip() or not evidence.strip():raise ValueError('Explicit termination reason, operator and evidence required')
    cancel(identity,operator,evidence)
    c=db()
    try:c.execute('UPDATE negotiations SET termination=? WHERE id=?',(reason,identity))
    finally:c.close()
