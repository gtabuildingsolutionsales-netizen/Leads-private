"""
Orchestrator — the 15-minute polling loop.

Each tick:
  1. Drain new leads -> research -> draft -> send -> mark 'emailed'.
  2. Drain unread replies -> strip clutter -> triage with Haiku -> alert or disqualify.
  3. Once per UTC day at REVIVAL_RUN_HOUR_UTC, send the 45-day revivals.

Designed to be idempotent at the lead level (status transitions gate work)
and non-fatal at the loop level (one bad lead never kills the tick).
"""

import os
import time
import traceback
from datetime import datetime, timezone

import requests

import ai_agent
import config
import database
import email_handler
import perplexity_researcher


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def alert_human(lead: dict, classification: dict, reply_text: str) -> None:
    """Notify a human that a qualified reply needs attention."""
    summary = (
        f"[QUALIFIED LEAD] {lead.get('company')} <{lead.get('email')}>\n"
        f"Reason: {classification.get('reason')}\n"
        f"Reply:\n{reply_text}"
    )
    print(f"\n=== HUMAN TAKEOVER REQUIRED ===\n{summary}\n================================\n")

    if config.SLACK_WEBHOOK_URL:
        try:
            requests.post(config.SLACK_WEBHOOK_URL, json={"text": summary}, timeout=10)
        except requests.RequestException as exc:
            print(f"[main] Slack post failed: {exc}")


# ---------------------------------------------------------------------------
# Step 1 — outbound icebreakers
# ---------------------------------------------------------------------------

def process_new_leads() -> None:
    leads = database.get_new_leads()
    if not leads:
        return
    print(f"[main] {len(leads)} new lead(s) to contact")

    for lead in leads:
        try:
            company = lead.get("company") or ""
            city = lead.get("city") or ""
            to_email = lead.get("email")
            if not to_email or not company:
                print(f"[main] Skipping malformed lead {lead.get('id')}")
                continue

            research = perplexity_researcher.research_company(company, city)
            if research != "NO_DATA":
                database.store_perplexity_summary(lead["id"], research)

            body = ai_agent.draft_icebreaker(lead, research)
            subject = f"Quick question about {company}"

            if email_handler.send_email(to_email, subject, body):
                database.update_lead_status(lead["id"], "emailed")
                print(f"[main] Emailed {company} <{to_email}>")
        except Exception:
            print(f"[main] Failed processing lead {lead.get('id')}:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Step 2 — inbound triage
# ---------------------------------------------------------------------------

def process_replies() -> None:
    replies = email_handler.get_unread_replies()
    if not replies:
        return
    print(f"[main] {len(replies)} unread reply/replies")

    for reply in replies:
        try:
            sender = reply["from_email"]
            lead = database.get_lead_by_email(sender)
            if lead is None:
                print(f"[main] Reply from unknown sender {sender} — ignoring")
                continue

            if not reply["clean_body"].strip():
                print(f"[main] Empty reply body from {sender} — alerting human")
                alert_human(lead, {"reason": "Empty body after clutter strip"}, reply["body"])
                continue

            verdict = ai_agent.evaluate_reply(reply["clean_body"])
            classification = verdict.get("classification")
            print(f"[main] {sender} -> {classification}")

            if classification == "Disqualified_Problem_Deal":
                database.update_lead_status(lead["id"], "disqualified")
            elif classification == "Qualified_Interested":
                database.update_lead_status(lead["id"], "qualified")
                alert_human(lead, verdict, reply["clean_body"])
        except Exception:
            print(f"[main] Failed processing reply from {reply.get('from_email')}:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Step 3 — daily revivals
# ---------------------------------------------------------------------------

def _read_revival_marker() -> str | None:
    if not os.path.exists(config.REVIVAL_STATE_FILE):
        return None
    with open(config.REVIVAL_STATE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip() or None


def _write_revival_marker(today_str: str) -> None:
    with open(config.REVIVAL_STATE_FILE, "w", encoding="utf-8") as f:
        f.write(today_str)


def maybe_run_revivals() -> None:
    """Run revivals once per UTC day, at or after REVIVAL_RUN_HOUR_UTC."""
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    if now.hour < config.REVIVAL_RUN_HOUR_UTC:
        return
    if _read_revival_marker() == today:
        return

    leads = database.get_45_day_revivals()
    print(f"[main] Daily revival pass — {len(leads)} ghosted lead(s) at 45 days")

    for lead in leads:
        try:
            to_email = lead.get("email")
            if not to_email:
                continue
            body = ai_agent.draft_revival_email(lead)
            subject = f"Quick check-in — {lead.get('company', 'your project')}"
            if email_handler.send_email(to_email, subject, body):
                database.update_lead_status(lead["id"], "revived")
                print(f"[main] Revival sent to {lead.get('company')} <{to_email}>")
        except Exception:
            print(f"[main] Failed reviving lead {lead.get('id')}:\n{traceback.format_exc()}")

    _write_revival_marker(today)


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

def tick() -> None:
    process_new_leads()
    process_replies()
    maybe_run_revivals()


def main() -> None:
    print(f"[main] Triple M lead-gen worker starting (interval={config.POLL_INTERVAL_SECONDS}s)")
    while True:
        start = time.monotonic()
        try:
            tick()
        except Exception:
            print(f"[main] Tick crashed:\n{traceback.format_exc()}")
        elapsed = time.monotonic() - start
        sleep_for = max(0, config.POLL_INTERVAL_SECONDS - elapsed)
        print(f"[main] Tick done in {elapsed:.1f}s; sleeping {sleep_for:.0f}s")
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
