"""
Perplexity sniper — one-sentence personalization fact per lead.

Returns a short blurb the icebreaker drafter can weave into sentence one,
or the literal string 'NO_DATA' when nothing concrete turns up.
"""

import requests

import config

_API_URL = "https://api.perplexity.ai/chat/completions"
_MODEL = "sonar-small-online"  # per spec; swap for your tier if needed
_TIMEOUT_S = 20


def research_company(company_name: str, city: str) -> str:
    """
    Ask Perplexity for a one-sentence project/review summary.

    Returns 'NO_DATA' on any failure or empty result, so the caller can
    safely treat it as "no personalization available".
    """
    if not config.PERPLEXITY_API_KEY:
        print("[perplexity] PERPLEXITY_API_KEY not set; skipping research")
        return "NO_DATA"

    prompt = (
        f"Search the web for the company '{company_name}' in '{city}'. "
        "Return a 1-sentence summary of a specific recent construction project "
        "they completed or a positive review. If nothing specific is found, "
        "output exactly 'NO_DATA'."
    )

    headers = {
        "Authorization": f"Bearer {config.PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = requests.post(_API_URL, headers=headers, json=payload, timeout=_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        summary = data["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        print(f"[perplexity] Lookup failed for {company_name}: {exc}")
        return "NO_DATA"

    if not summary or "NO_DATA" in summary.upper():
        return "NO_DATA"
    return summary
