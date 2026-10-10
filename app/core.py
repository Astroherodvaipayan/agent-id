import hashlib
import json
import os
import sqlite3
import smtplib
import ssl
import re
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

PACKAGE = "1 Instagram Reel + 1 Story + 30 days organic reposting; no paid usage or exclusivity"
CEILING = 5_000_000

def db():
    conn = sqlite3.connect(os.getenv("DATABASE_PATH", "agentid.sqlite3"), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS campaign (id INTEGER PRIMARY KEY CHECK(id=1), idea TEXT NOT NULL, creator TEXT NOT NULL, brief TEXT NOT NULL, budget_paise INTEGER NOT NULL, evidence TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, creator_intro TEXT NOT NULL DEFAULT '', target_markets TEXT NOT NULL DEFAULT '[]');
    CREATE TABLE IF NOT EXISTS guardrail_review (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, findings_json TEXT NOT NULL, status TEXT NOT NULL, reviewer TEXT, mitigation TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS approval (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, amount_paise INTEGER NOT NULL, approver TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY CHECK(id=1), operation_id TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL, amount_paise INTEGER NOT NULL, status TEXT NOT NULL, message_id TEXT NOT NULL, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS inbound (uid TEXT PRIMARY KEY, sender TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, thread_match INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'received', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS reconciliation (id INTEGER PRIMARY KEY, operation_id TEXT NOT NULL, status TEXT NOT NULL, evidence TEXT NOT NULL, operator TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS inbox_cursor (mailbox TEXT PRIMARY KEY, uidvalidity TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    migrations = {
        "campaign": {"creator_intro": "TEXT NOT NULL DEFAULT ''", "target_markets": "TEXT NOT NULL DEFAULT '[]'"},
        "inbound": {"thread_match": "INTEGER NOT NULL DEFAULT 0"},
        "approval": {"payload_json": "TEXT NOT NULL DEFAULT ''", "payload_hash": "TEXT NOT NULL DEFAULT ''"},
    }
    for table, columns in migrations.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    legacy = conn.execute("SELECT revision FROM campaign WHERE id=1").fetchone()
    if legacy:
        conn.execute("INSERT OR IGNORE INTO guardrail_review(id,revision,findings_json,status) VALUES (1,?,?,?)", (legacy["revision"], '["Legacy draft requires target-market review"]', "pending"))
    return conn

def event(c, kind, detail):
    c.execute("INSERT INTO events(kind,detail) VALUES (?,?)", (kind, json.dumps(detail, sort_keys=True)))

def proposal_text(idea, amount_paise, creator_intro=""):
    # Campaign idea and model prose are review data, never outbound instructions.
    opening = "Would you consider a collaboration for an upcoming campaign?"
    return f"Hello,\n\n{opening}\n\nPackage: {PACKAGE}.\nProposed fee: INR {amount_paise / 100:,.2f}.\n\nThis is a nonbinding proposal. No contract, payment, paid usage or exclusivity is agreed by this message. Please reply with your thoughts.\n"

def frozen_payload(idea, recipient, amount_paise, creator_intro=""):
    return {"recipient": recipient, "from": os.environ["SMTP_FROM"], "reply_to": os.environ["BRAND_REPLY_TO"], "subject": "Nonbinding collaboration proposal", "body": proposal_text(idea, amount_paise, creator_intro), "amount_paise": amount_paise, "package": PACKAGE}

def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

def draft(idea, creator, budget_paise, model_brief=None, creator_intro="", target_markets=(), avoid_terms=(), model_risk_flags=()):
    allowed = os.environ["CREATOR_EMAIL"].strip().lower()
    if creator.strip().lower() != allowed:
        raise ValueError("Creator is outside the configured recipient allowlist")
    if not idea.strip() or budget_paise < 0 or budget_paise > CEILING:
        raise ValueError("Invalid idea or budget")
    if not target_markets or not all(isinstance(x, str) and x.strip() for x in target_markets):
        raise ValueError("At least one target market is required for guardrail review")
    if len(creator_intro) > 600 or "\n" in creator_intro:
        raise ValueError("Invalid creator introduction")
    hard_flags = [f"Avoid term appears in campaign copy: {term}" for term in avoid_terms if term.strip() and term.casefold() in (idea + " " + creator_intro).casefold()]
    if re.search(r"\b(?:INR|paid usage|exclusiv\w*|contract|guarantee\w*|payment)\b|₹", creator_intro, re.I):
        hard_flags.append("Creator introduction includes a term reserved for the fixed backend proposal")
    findings = list(hard_flags)
    findings.extend(str(flag)[:300] for flag in model_risk_flags)
    if not model_brief:
        findings.append("Model market assessment not run; operator must review each target market")
    brief = f"Campaign idea: {idea.strip()}\n"
    if model_brief:
        brief += f"Model planning draft: {model_brief[:4000]}\n"
    brief += f"Package: {PACKAGE}\nSuggested budget: INR {budget_paise / 100:,.2f}. Human review required."
    evidence = "Synthetic planning heuristics only. Wild Samaj Instagram Insights not connected or verified."
    c = db()
    try:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM outbox WHERE id=1").fetchone():
            raise ValueError("Proposal slot already used; draft cannot be replaced")
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='negotiation_outbox'").fetchone() and c.execute("SELECT 1 FROM negotiation_outbox WHERE status NOT IN ('not_sent_reconciled','cancelled_before_dispatch','superseded_reconciled')").fetchone():
            raise ValueError("Creator financial holds exist; campaign cannot be replaced")
        old = c.execute("SELECT revision FROM campaign WHERE id=1").fetchone()
        revision = old[0] + 1 if old else 1
        c.execute("INSERT OR REPLACE INTO campaign(id,idea,creator,brief,budget_paise,evidence,revision,creator_intro,target_markets) VALUES (1,?,?,?,?,?,?,?,?)", (idea, allowed, brief, budget_paise, evidence, revision, creator_intro, json.dumps(list(target_markets))))
        c.execute("DELETE FROM approval")
        status = "blocked" if hard_flags else "pending"
        c.execute("INSERT OR REPLACE INTO guardrail_review(id,revision,findings_json,status) VALUES (1,?,?,?)", (revision, json.dumps(findings), status))
        event(c, "draft", {"revision": revision, "evidence": evidence, "target_markets": list(target_markets), "guardrail_findings": findings})
        c.execute("COMMIT")
        return {"brief": brief, "evidence": evidence, "revision": revision, "guardrail_findings": findings, "guardrail_status": status}
    except:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()

def latest_reply():
    c = db()
    try:
        row = c.execute("SELECT campaign.idea, inbound.body FROM campaign CROSS JOIN inbound WHERE campaign.id=1 AND inbound.state='complete' ORDER BY inbound.created_at DESC, inbound.rowid DESC LIMIT 1").fetchone()
        if not row:
            raise ValueError("No completed creator reply for this campaign")
        return dict(row)
    finally:
        c.close()

def review_guardrails(revision, reviewer, mitigation):
    if not reviewer.strip() or not mitigation.strip():
        raise ValueError("Reviewer and market-specific review note required")
    c = db()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT campaign.revision,guardrail_review.findings_json,guardrail_review.status,campaign.target_markets FROM campaign JOIN guardrail_review ON campaign.revision=guardrail_review.revision WHERE campaign.id=1 AND guardrail_review.id=1").fetchone()
        if not row or row["revision"] != revision:
            raise ValueError("Stale guardrail review")
        if row["status"] == "blocked":
            raise ValueError("Blocked avoid term requires a revised campaign draft")
        c.execute("UPDATE guardrail_review SET status='approved',reviewer=?,mitigation=? WHERE id=1", (reviewer.strip(), mitigation.strip()[:2000]))
        event(c, "market_guardrails_reviewed", {"revision": revision, "reviewer": reviewer, "target_markets": json.loads(row["target_markets"]), "findings": json.loads(row["findings_json"]), "mitigation": mitigation[:2000]})
        c.execute("COMMIT")
    except:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()

def approve(revision, amount_paise, approver, preview_hash):
    c = db()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM campaign WHERE id=1").fetchone()
        if not row or row["revision"] != revision:
            raise ValueError("Stale or missing draft")
        if not 0 <= amount_paise <= CEILING or not approver.strip():
            raise ValueError("Invalid approval")
        if amount_paise > row["budget_paise"]:
            raise ValueError("Proposal amount exceeds campaign budget")
        if c.execute("SELECT 1 FROM outbox WHERE id=1").fetchone():
            raise ValueError("Proposal slot already used")
        reviewed = c.execute("SELECT status,revision FROM guardrail_review WHERE id=1").fetchone()
        if not reviewed or reviewed["revision"] != revision or reviewed["status"] != "approved":
            raise ValueError("Target-market guardrails need operator review")
        payload = frozen_payload(row["idea"], row["creator"], amount_paise, row["creator_intro"])
        digest = payload_hash(payload)
        if not preview_hash or digest != preview_hash:
            raise ValueError("Absent or stale exact email preview hash")
        c.execute("INSERT OR REPLACE INTO approval(id,revision,amount_paise,approver,payload_json,payload_hash) VALUES (1,?,?,?,?,?)", (revision, amount_paise, approver.strip(), json.dumps(payload, sort_keys=True), digest))
        event(c, "operator_approval", {"revision": revision, "amount_paise": amount_paise, "approver": approver})
        c.execute("COMMIT")
    except:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()

def proposal_payload(amount_paise):
    c = db()
    try:
        row = c.execute("SELECT campaign.revision, approval.amount_paise, approval.payload_json, approval.payload_hash FROM campaign JOIN approval ON campaign.revision=approval.revision WHERE campaign.id=1 AND approval.id=1").fetchone()
        if not row or row["amount_paise"] != amount_paise:
            raise ValueError("No matching current operator approval")
        if not row["payload_json"] or not row["payload_hash"]:
            raise ValueError("Legacy approval requires renewed exact-preview approval")
        return json.loads(row["payload_json"])
    finally:
        c.close()

def preview_payload(amount_paise):
    if not 0 <= amount_paise <= CEILING:
        raise ValueError("Amount outside backend ceiling")
    c = db()
    try:
        row = c.execute("SELECT idea,creator,revision,creator_intro,budget_paise FROM campaign WHERE id=1").fetchone()
        if not row:
            raise ValueError("No campaign draft")
        if amount_paise > row["budget_paise"]:
            raise ValueError("Proposal amount exceeds campaign budget")
        payload = frozen_payload(row["idea"], row["creator"], amount_paise, row["creator_intro"])
        return {**payload, "revision": row["revision"], "preview_hash": payload_hash(payload)}
    finally:
        c.close()

def reserve(operation_id, amount_paise):
    if not operation_id or not 0 <= amount_paise <= CEILING:
        raise ValueError("Invalid operation or amount")
    c = db()
    try:
        c.execute("BEGIN IMMEDIATE")
        old = c.execute("SELECT * FROM outbox WHERE id=1").fetchone()
        if old:
            if old["operation_id"] != operation_id or old["amount_paise"] != amount_paise:
                raise ValueError("Proposal slot conflict")
            c.execute("COMMIT")
            return dict(old), False
        approved = c.execute("SELECT approval.*, campaign.budget_paise FROM approval JOIN campaign ON campaign.revision=approval.revision WHERE approval.id=1 AND campaign.id=1").fetchone()
        if not approved or approved["amount_paise"] != amount_paise or not approved["payload_json"] or not approved["payload_hash"]:
            raise ValueError("No matching current operator approval")
        if amount_paise > approved["budget_paise"]:
            raise ValueError("Proposal amount exceeds campaign budget")
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='negotiation_outbox'").fetchone():
            reserved = c.execute("SELECT COALESCE(SUM(amount_paise),0) FROM negotiation_outbox WHERE status NOT IN ('not_sent_reconciled','cancelled_before_dispatch','superseded_reconciled')").fetchone()[0]
            if reserved + amount_paise > approved["budget_paise"]:
                raise ValueError("Shared campaign budget exhausted")
        digest = approved["payload_hash"]
        if payload_hash(json.loads(approved["payload_json"])) != digest:
            raise ValueError("Approved payload integrity failure")
        message_id = make_msgid(domain=os.environ["SMTP_FROM"].split("@")[-1])
        c.execute("INSERT INTO outbox(id,operation_id,payload_hash,amount_paise,status,message_id) VALUES (1,?,?,?,?,?)", (operation_id, digest, amount_paise, "reserved", message_id))
        event(c, "outbox_reserved", {"operation_id": operation_id, "payload_hash": digest})
        c.execute("COMMIT")
        return dict(c.execute("SELECT * FROM outbox WHERE id=1").fetchone()), True
    except:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()

def update_outbox(status, detail):
    c = db()
    try:
        c.execute("UPDATE outbox SET status=?, detail=? WHERE id=1", (status, detail))
        event(c, "delivery_state", {"status": status, "detail": detail})
    finally:
        c.close()

def record_reconciliation(operation_id, status, evidence, operator):
    if status not in ("provider_accepted", "provider_confirmed_not_sent", "inbox_confirmed") or not evidence.strip() or not operator.strip():
        raise ValueError("Invalid reconciliation evidence")
    c = db()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT operation_id,message_id,status FROM outbox WHERE id=1").fetchone()
        if not row or row["operation_id"] != operation_id:
            raise ValueError("Unknown operation")
        state = {"provider_accepted": "accepted_by_provider_reconciled", "provider_confirmed_not_sent": "not_sent_reconciled", "inbox_confirmed": "delivery_confirmed"}[status]
        c.execute("INSERT INTO reconciliation(operation_id,status,evidence,operator) VALUES (?,?,?,?)", (operation_id,status,evidence[:4000],operator))
        c.execute("UPDATE outbox SET status=?, detail=? WHERE id=1", (state, "Operator-recorded provider evidence; see reconciliation log"))
        event(c, "operator_reconciliation", {"operation_id": operation_id, "message_id": row["message_id"], "status": status, "evidence": evidence[:4000], "operator": operator})
        c.execute("COMMIT")
        return {"message_id": row["message_id"], "reconciled_status": status, "outbox_status": state}
    except:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()

def send_nonbinding_proposal(operation_id: str, amount_paise: int):
    """Narrow MCP handler. This function never accepts recipient or freeform body."""
    record, fresh = reserve(operation_id, amount_paise)
    if not fresh:
        return {"status": record["status"], "message_id": record["message_id"], "duplicate": True}
    payload = proposal_payload(amount_paise)
    if payload_hash(payload) != record["payload_hash"]:
        update_outbox("unknown", "Approved payload changed after reservation; reconcile before any action")
        raise RuntimeError("Approved payload integrity failure")
    msg = EmailMessage()
    msg["From"] = payload["from"]
    msg["To"] = payload["recipient"]
    msg["Reply-To"] = payload["reply_to"]
    msg["Subject"] = payload["subject"]
    msg["Message-ID"] = record["message_id"]
    msg["X-Agent-Operation-ID"] = operation_id
    msg.set_content(payload["body"])
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=20) as smtp:
            smtp.ehlo()
            if os.getenv("SMTP_STARTTLS", "true").lower() == "true":
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if os.getenv("SMTP_USERNAME"):
                smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
        update_outbox("accepted_by_smtp", "Provider accepted submission; inbox receipt unverified")
        return {"status": "accepted_by_smtp", "message_id": record["message_id"]}
    except Exception as exc:
        update_outbox("unknown", type(exc).__name__ + ": reconcile Sent mailbox or provider record before retry")
        raise

def ingest(uid, sender, subject, body, references=""):
    creator = os.environ["CREATOR_EMAIL"].lower()
    if sender.lower() != creator:
        raise ValueError("Sender outside creator allowlist")
    c = db()
    try:
        c.execute("INSERT OR IGNORE INTO inbound(uid,sender,subject,body) VALUES (?,?,?,?)", (uid, sender, subject, body))
        row = c.execute("SELECT state FROM inbound WHERE uid=?", (uid,)).fetchone()
        if row["state"] in ("complete", "quarantined"):
            return {"duplicate": True}
        sent = c.execute("SELECT message_id FROM outbox WHERE id=1").fetchone()
        seeded_thread = os.getenv("INITIAL_THREAD_MESSAGE_ID", "")
        id_pattern = r"<[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+>"
        message_ids = {token for token in references.split() if re.fullmatch(id_pattern, token)}
        threaded = bool((sent and sent["message_id"] in message_ids) or (seeded_thread and seeded_thread in message_ids))
        # IMAP From and message headers alone are not provider-authenticated identity.
        c.execute("BEGIN IMMEDIATE")
        event(c, "inbound_quarantined", {"uid": uid, "thread_match": threaded, "reason": "Provider authentication evidence and operator review required"})
        c.execute("UPDATE inbound SET state='quarantined', thread_match=? WHERE uid=?", (int(threaded), uid))
        c.execute("COMMIT")
        return {"duplicate": False, "quarantined": True, "thread_match": threaded}
    finally:
        c.close()

def verify_inbound(uid, source, provider_record_id, sender_verified, thread_verified, operator):
    if source not in ("provider_log", "controlled_inbox_manual") or not provider_record_id.strip() or not operator.strip() or not sender_verified or not thread_verified:
        raise ValueError("Structured sender and thread verification required")
    c = db()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT state,thread_match FROM inbound WHERE uid=?", (uid,)).fetchone()
        if not row or row["state"] != "quarantined":
            raise ValueError("No quarantined inbound message")
        if not row["thread_match"]:
            raise ValueError("Message does not reference the sent proposal Message-ID")
        c.execute("UPDATE inbound SET state='complete' WHERE uid=?", (uid,))
        event(c, "inbound_operator_verified", {"uid": uid, "source": source, "provider_record_id": provider_record_id[:2000], "sender_verified": True, "thread_verified": True, "operator": operator, "evidence_type": "manual_operator_review"})
        c.execute("COMMIT")
    except:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()
