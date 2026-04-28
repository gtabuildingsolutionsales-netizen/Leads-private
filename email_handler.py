"""
IMAP/SMTP comm engine.

The token-saver here is `strip_email_clutter`: replies often come back with
the entire prior thread, signatures, and disclaimers tacked on. We send
only the prospect's actual reply to the LLM.
"""

import email
import imaplib
import re
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parseaddr

import config


# ---------------------------------------------------------------------------
# Clutter stripping
# ---------------------------------------------------------------------------

# Anything from these markers down is reply history / signature / disclaimer.
# Order matters — first match wins.
_CUTOFF_PATTERNS = [
    # "On Mon, Apr 28, 2026 at 10:14 AM John Doe <john@x.com> wrote:"
    re.compile(r"^On\s.{0,200}\swrote:\s*$", re.MULTILINE | re.IGNORECASE),
    # Outlook/Exchange forwarded headers
    re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*From:\s.+\s*$", re.MULTILINE),
    # Standard signature delimiter (per RFC 3676)
    re.compile(r"^-- \s*$", re.MULTILINE),
    # Mobile signatures
    re.compile(r"^Sent from my\s.+$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^Get Outlook for\s.+$", re.MULTILINE | re.IGNORECASE),
    # Legal disclaimers
    re.compile(r"^\s*(CONFIDENTIALITY|DISCLAIMER|LEGAL NOTICE|PRIVILEGED)[\s:].*$",
               re.MULTILINE | re.IGNORECASE),
]

# Quoted-reply lines (">", ">>", etc.)
_QUOTED_LINE = re.compile(r"^\s*>+.*$", re.MULTILINE)


def strip_email_clutter(email_body: str) -> str:
    """
    Aggressively trim a reply down to just the prospect's new text.

    Strategy: find the earliest "this is the start of the prior thread or
    signature" marker and chop everything from there. Then drop lone
    quoted-reply lines and collapse whitespace.
    """
    if not email_body:
        return ""

    earliest_cut = len(email_body)
    for pattern in _CUTOFF_PATTERNS:
        match = pattern.search(email_body)
        if match and match.start() < earliest_cut:
            earliest_cut = match.start()

    body = email_body[:earliest_cut]
    body = _QUOTED_LINE.sub("", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


# ---------------------------------------------------------------------------
# IMAP — fetch unread replies
# ---------------------------------------------------------------------------

def _decode(raw: bytes | str) -> str:
    """Header decoder that tolerates mixed encodings."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    parts = decode_header(raw)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


_TAG_RE = re.compile(r"<[^>]+>")
_HTML_BREAK_RE = re.compile(r"</(p|div|br|tr|li)\s*>", re.IGNORECASE)


def _html_to_text(html: str) -> str:
    """Crude but dependency-free HTML stripping for emails that lack text/plain."""
    text = _HTML_BREAK_RE.sub("\n", html)
    text = _TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_body(msg: email.message.Message) -> str:
    """
    Prefer text/plain; fall back to text/html (tags stripped) if that's all
    the sender shipped. Skip attachments.
    """
    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ctype == "text/plain" and not plain:
                plain = decoded
            elif ctype == "text/html" and not html:
                html = decoded
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            html = decoded
        else:
            plain = decoded

    return plain if plain else _html_to_text(html)


def get_unread_replies() -> list[dict]:
    """
    Fetch UNSEEN messages and mark them read.

    Returns dicts with: from_email, subject, body (raw), clean_body (stripped).
    Returns [] if the mailbox is empty or unreachable — never raises.
    """
    if not (config.EMAIL_USER and config.EMAIL_PASS):
        return []

    try:
        with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as imap:
            imap.login(config.EMAIL_USER, config.EMAIL_PASS)
            imap.select("INBOX")
            status, data = imap.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return []

            replies = []
            for uid in data[0].split():
                status, msg_data = imap.fetch(uid, "(RFC822)")
                if status != "OK":
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                _, from_email = parseaddr(msg.get("From", ""))
                body = _extract_body(msg)
                replies.append({
                    "from_email": from_email.lower(),
                    "subject": _decode(msg.get("Subject", "")),
                    "body": body,
                    "clean_body": strip_email_clutter(body),
                })
            return replies
    except (imaplib.IMAP4.error, OSError) as exc:
        print(f"[email_handler] IMAP fetch failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# SMTP — send
# ---------------------------------------------------------------------------

def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send a plaintext email. Returns True on success."""
    if not (config.EMAIL_USER and config.EMAIL_PASS):
        print(f"[email_handler] Skipping send to {to_email} — SMTP credentials not set")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"{config.FROM_NAME} <{config.FROM_EMAIL}>"
    msg["To"] = to_email

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(config.EMAIL_USER, config.EMAIL_PASS)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        print(f"[email_handler] SMTP send to {to_email} failed: {exc}")
        return False
