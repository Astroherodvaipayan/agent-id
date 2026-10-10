import email
import imaplib
import os
from email.header import decode_header, make_header
from email.utils import parseaddr
from .core import db, ingest
from . import negotiations

def poll():
    count = 0
    with imaplib.IMAP4_SSL(os.environ["IMAP_HOST"], int(os.getenv("IMAP_PORT", "993"))) as box:
        box.login(os.environ["IMAP_USERNAME"], os.environ["IMAP_PASSWORD"])
        box.select("INBOX", readonly=True)
        typ, validity = box.response("UIDVALIDITY")
        if typ != "UIDVALIDITY" or not validity or not validity[0]:
            raise RuntimeError("IMAP UIDVALIDITY unavailable")
        uidvalidity = validity[0].decode()
        with db() as c:
            old = c.execute("SELECT uidvalidity FROM inbox_cursor WHERE mailbox='INBOX'").fetchone()
            if old and old[0] != uidvalidity:
                raise RuntimeError("IMAP UIDVALIDITY changed; operator reconciliation required")
            c.execute("INSERT OR IGNORE INTO inbox_cursor(mailbox,uidvalidity) VALUES ('INBOX',?)", (uidvalidity,))
        typ, data = box.uid("search", None, "ALL")
        if typ != "OK":
            raise RuntimeError("IMAP search failed")
        for uid in data[0].split():
            typ, parts = box.uid("fetch", uid, "(BODY.PEEK[])")
            if typ != "OK":
                continue
            raw = next((part[1] for part in parts if isinstance(part, tuple)), None)
            if raw is None:
                continue
            msg = email.message_from_bytes(raw)
            sender = parseaddr(msg.get("From", ""))[1]
            if sender.lower() not in negotiations.allowlist():
                continue
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            body = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
            references = " ".join((msg.get("In-Reply-To", ""), msg.get("References", "")))
            result = negotiations.ingest_reply(f"{uidvalidity}:{uid.decode()}", sender, body[:20000], references)
            if not result.get('routed') and not result.get('duplicate'):
                if sender.lower() != os.environ.get('CREATOR_EMAIL','').lower():continue
                result = ingest(f"{uidvalidity}:{uid.decode()}", sender, subject, body[:20000], references)
            if not result["duplicate"]:
                count += 1
    return count
