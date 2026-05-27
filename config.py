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
