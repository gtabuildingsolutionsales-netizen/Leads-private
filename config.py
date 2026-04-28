"""
Static configuration for the Triple M lead-gen pipeline.

Everything that might need tuning lives here so the rest of the codebase
can stay free of magic strings. No "self-learning" or runtime mutation —
underwriting rules are static by design.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Geography / underwriting gates
# ---------------------------------------------------------------------------
TARGET_CITIES = ["Toronto", "Mississauga", "Brampton"]
MAX_LTV_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# Anthropic models
#
# The architect originally specified "Claude 3 Haiku" and "Claude 3.5 Sonnet".
# Both were retired by Anthropic before this build, so we use the official
# drop-in replacements:
#   Haiku 3   -> claude-haiku-4-5  (cheap triage)
#   Sonnet 3.5 -> claude-sonnet-4-6 (drafting)
# Same intelligence-vs-cost split, current model IDs.
# ---------------------------------------------------------------------------
TRIAGE_MODEL = "claude-haiku-4-5"
DRAFTING_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
ICEBREAKER_SYSTEM_PROMPT = (
    "You are a lending partner at Triple M. You are speaking peer-to-peer "
    "with general contractors and real estate investors. Keep it to 3-4 "
    "sentences. Use contractions. NEVER ask for paperwork (appraisals, "
    "credit scores) in the first email. Ask casually about the loan amount "
    "and property value to see if we can structure something creative. End "
    "with a low-friction offer for a 5-minute call."
)

TRIAGE_SYSTEM_PROMPT = (
    "Analyze this email reply. If they mention 100% financing, zero money "
    "down, or that other lenders pulled out, tag as Disqualified_Problem_Deal. "
    "If they provide numbers, property details, or ask for next steps, tag "
    "as Qualified_Interested."
)

REVIVAL_SYSTEM_PROMPT = (
    "You are a lending partner at Triple M following up with a prospect who "
    "went quiet 45 days ago. Write exactly two sentences. Ask if their bank "
    "financing fell through and offer fast bridge capital. Use contractions. "
    "Peer-to-peer tone, no pressure."
)

# ---------------------------------------------------------------------------
# Loop cadence
# ---------------------------------------------------------------------------
POLL_INTERVAL_SECONDS = 15 * 60          # 15 minutes
REVIVAL_RUN_HOUR_UTC = 13                # ~9am Eastern, runs once per UTC day

# ---------------------------------------------------------------------------
# Credentials (loaded from .env — never hardcode)
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
FROM_NAME = os.getenv("FROM_NAME", "Triple M Lending")
FROM_EMAIL = os.getenv("FROM_EMAIL", EMAIL_USER)

# Optional: post qualified leads to a Slack webhook. If unset, alerts go to stdout.
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Where the daily revival marker lives (so we only run revivals once per day)
REVIVAL_STATE_FILE = ".last_revival_run"
