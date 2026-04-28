"""
Supabase controller.

Assumed `leads` table schema:
    id                   bigint / uuid (PK)
    email                text
    company              text
    city                 text         -- needed by perplexity_researcher
    status               text         -- 'new' | 'emailed' | 'ghosted' | 'qualified' | 'disqualified'
    last_contacted_date  date
    perplexity_summary   text         -- optional, populated when we research
"""

from datetime import date, timedelta
from supabase import create_client, Client

import config

_client: Client | None = None


def _get_client() -> Client:
    """Lazy singleton — avoids constructing the client at import time."""
    global _client
    if _client is None:
        if not config.SUPABASE_URL or not config.SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client


def get_new_leads() -> list[dict]:
    """Fetch leads we have never contacted (status == 'new')."""
    resp = _get_client().table("leads").select("*").eq("status", "new").execute()
    return resp.data or []


def get_lead_by_email(email_address: str) -> dict | None:
    """Look up a single lead by email address. Returns None if absent."""
    resp = (
        _get_client()
        .table("leads")
        .select("*")
        .ilike("email", email_address)
        .limit(1)
        .execute()
    )
    return (resp.data or [None])[0]


def update_lead_status(lead_id, status: str) -> None:
    """Update a lead's status and stamp last_contacted_date when we just emailed."""
    payload = {"status": status}
    if status in ("emailed", "revived"):
        payload["last_contacted_date"] = date.today().isoformat()
    _get_client().table("leads").update(payload).eq("id", lead_id).execute()


def store_perplexity_summary(lead_id, summary: str) -> None:
    """Cache the research blurb so we don't re-query Perplexity on retries."""
    _get_client().table("leads").update({"perplexity_summary": summary}).eq("id", lead_id).execute()


def get_45_day_revivals() -> list[dict]:
    """Leads that went quiet exactly 45 days ago — the revival cohort."""
    target = (date.today() - timedelta(days=45)).isoformat()
    resp = (
        _get_client()
        .table("leads")
        .select("*")
        .eq("status", "ghosted")
        .eq("last_contacted_date", target)
        .execute()
    )
    return resp.data or []
