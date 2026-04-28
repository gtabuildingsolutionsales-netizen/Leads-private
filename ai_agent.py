"""
The brain.

Two responsibilities:
  1. Triage replies with cheap Haiku and return a structured classification.
  2. Draft outbound emails (icebreaker + 45-day revival) with Sonnet.

System prompts are cached so we pay full price once and ~10% on every
subsequent call within the 5-minute window. The triage system prompt is
short and may not hit the cache minimum on Haiku — that's fine, no error.
"""

import json
import anthropic

import config

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY must be set in .env")
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Triage — Haiku
# ---------------------------------------------------------------------------

_TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": ["Qualified_Interested", "Disqualified_Problem_Deal"],
        },
        "reason": {
            "type": "string",
            "description": "One short sentence explaining the call.",
        },
    },
    "required": ["classification", "reason"],
    "additionalProperties": False,
}


def evaluate_reply(email_text: str) -> dict:
    """
    Classify a (cleaned) reply into Qualified_Interested or
    Disqualified_Problem_Deal. Returns {'classification': ..., 'reason': ...}.

    On any API failure we default to Qualified_Interested + a reason flag,
    so a transient error never silently buries a hot lead — it escalates
    to human review.
    """
    client = _get_client()
    try:
        resp = client.messages.create(
            model=config.TRIAGE_MODEL,
            max_tokens=256,
            system=[{
                "type": "text",
                "text": config.TRIAGE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": email_text}],
            output_config={"format": {"type": "json_schema", "schema": _TRIAGE_SCHEMA}},
        )
        text_block = next((b for b in resp.content if b.type == "text"), None)
        if text_block is None:
            raise ValueError("No text block in triage response")
        return json.loads(text_block.text)
    except (anthropic.APIError, json.JSONDecodeError, ValueError) as exc:
        print(f"[ai_agent] Triage failed, escalating to human: {exc}")
        return {
            "classification": "Qualified_Interested",
            "reason": f"Triage error — needs manual review: {exc}",
        }


# ---------------------------------------------------------------------------
# Drafting — Sonnet
# ---------------------------------------------------------------------------

def _draft(system_prompt: str, user_prompt: str, max_tokens: int = 600) -> str:
    """Shared Sonnet drafter with cached system prompt."""
    resp = _get_client().messages.create(
        model=config.DRAFTING_MODEL,
        max_tokens=max_tokens,
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return text.strip()


def draft_icebreaker(lead_data: dict, perplexity_data: str) -> str:
    """
    First-touch email body. If Perplexity found a real project, weave it
    into the opening sentence; otherwise fall back to a generic-but-warm
    opener.
    """
    company = lead_data.get("company", "your team")
    city = lead_data.get("city", "")

    if perplexity_data and perplexity_data != "NO_DATA":
        user_prompt = (
            f"Write a first-touch email to a contact at {company} ({city}). "
            f"Open the FIRST sentence by referencing this specific fact about "
            f"them, naturally and peer-to-peer (do not quote it verbatim): "
            f"\"{perplexity_data}\"\n\n"
            "Then follow the system prompt's structure: ask casually about "
            "loan amount and property value, end with a 5-minute call offer. "
            "Output only the email body — no subject line, no signature."
        )
    else:
        user_prompt = (
            f"Write a first-touch email to a contact at {company} "
            f"{f'in {city} ' if city else ''}"
            "without any specific personalization fact available. Keep it warm "
            "and credible — reference the local market generally. Follow the "
            "system prompt's structure. Output only the email body — no "
            "subject line, no signature."
        )

    return _draft(config.ICEBREAKER_SYSTEM_PROMPT, user_prompt)


def draft_revival_email(lead_data: dict) -> str:
    """45-day check-in. Two sentences, per the system prompt."""
    company = lead_data.get("company", "your team")
    user_prompt = (
        f"Write the 45-day check-in to a contact at {company}. "
        "Two sentences exactly. Output only the email body."
    )
    return _draft(config.REVIVAL_SYSTEM_PROMPT, user_prompt, max_tokens=200)
