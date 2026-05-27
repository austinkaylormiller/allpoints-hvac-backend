"""Configuration flags and environment variable loading.

The USE_STUB_* flags control whether endpoints use stub
implementations or real integrations. Env vars are loaded from .env
in local dev (via python-dotenv) and from the Railway dashboard in
deployed environments.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

USE_STUB_VENDOR_MESSAGE = os.getenv("USE_STUB_VENDOR_MESSAGE", "false").lower() == "true"

DATA_DIR = Path(__file__).parent / "data"
MESSAGES_JSONL_PATH = DATA_DIR / "messages.jsonl"

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "Booker AI <austin@getbookerai.com>")

_raw_recipients = os.getenv("OFFICE_EMAIL_RECIPIENTS", "")
OFFICE_EMAIL_RECIPIENTS = [
    r.strip() for r in _raw_recipients.split(",") if r.strip()
]

CLIENT_BUSINESS_NAME = os.getenv("CLIENT_BUSINESS_NAME", "AllPoints HVAC")
MANNY_BUSINESS_NAME = os.getenv("MANNY_BUSINESS_NAME", "Manny's Oil Company")

BOOKER_WEBHOOK_URL = os.getenv("BOOKER_WEBHOOK_URL")
BOOKER_WEBHOOK_SECRET = os.getenv("BOOKER_WEBHOOK_SECRET")

POST_CALL_WEBHOOK_FORWARDING_ENABLED = (
    os.getenv("POST_CALL_WEBHOOK_FORWARDING_ENABLED", "true").lower() == "true"
)

# --- Urgent call orchestration ---

# Twilio account credentials. Same Twilio account used across PROD
# and TEST — the differentiation is which phone number gets called
# (URGENT_CALL_RECIPIENT_PHONE) and how fast the retry loop runs
# (URGENT_CALL_FAST_MODE).
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

# Supabase. Service-role key (bypasses RLS); the urgent_call_attempts
# table lives in the shared Booker dashboard database.
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Phone number that receives urgent calls. PROD: Manny's cell.
# TEST: Austin's cell.
URGENT_CALL_RECIPIENT_PHONE = os.getenv("URGENT_CALL_RECIPIENT_PHONE")

# Compress the retry timings for manual integration testing.
# PROD: unset/false → 90s wait per call, 30s between calls (max
# flow time ~5.5 min). TEST may set this to true → 10s/3s
# (max flow time ~30s).
URGENT_CALL_FAST_MODE = (
    os.getenv("URGENT_CALL_FAST_MODE", "false").lower() == "true"
)

# Public base URL the FastAPI app is reachable at. Used to build
# absolute callback URLs for Twilio (TwiML fetch, Gather action,
# status callback). Twilio cannot reach localhost or private
# addresses, so this must be the public custom domain.
# PROD: https://allpoints-api.getbookerai.com
# TEST: https://allpoints-api-test.getbookerai.com
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
