"""Thin wrapper around the Twilio SDK.

Two responsibilities:
1. Place an outbound call (`create_urgent_call`) with the right
   TwiML fetch URL, Gather action URL, and status callback URL.
2. Generate the TwiML XML the call should play
   (`generate_urgent_twiml` and `generate_thank_you_twiml`).

The orchestration in services/urgent_call.py composes these.
"""

import logging
from urllib.parse import quote

from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Gather, VoiceResponse

import config

logger = logging.getLogger(__name__)

# Voice + Gather settings — match the existing Make.com TwiML bin so
# the recipient hears the same call experience as before.
_VOICE = "Polly.Joanna-Neural"
_GATHER_TIMEOUT_SECONDS = 15
_GATHER_NUM_DIGITS = 1

_URGENT_MESSAGE = (
    "This is an urgent notification from AllPoints HVAC. "
    "An urgent service request has been received. "
    "Please check your email immediately for full customer "
    "details and contact information. "
    "Press any button to confirm you received this message."
)

_THANK_YOU_MESSAGE = "Thank you, confirmation received. Goodbye."
_NO_DIGIT_MESSAGE = "No confirmation received. Goodbye."


def _twilio_client() -> TwilioClient:
    """Build a Twilio client from config; raise if creds are unset."""
    if not config.TWILIO_ACCOUNT_SID or not config.TWILIO_AUTH_TOKEN:
        raise RuntimeError(
            "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must both be set"
        )
    return TwilioClient(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)


def _callback_url(path: str, attempt_id: str) -> str:
    """Build an absolute Twilio callback URL with attempt_id query."""
    if not config.PUBLIC_BASE_URL:
        raise RuntimeError("PUBLIC_BASE_URL must be set for Twilio callbacks")
    return f"{config.PUBLIC_BASE_URL}{path}?attempt_id={quote(attempt_id)}"


def create_urgent_call(to_number: str, attempt_id: str) -> str:
    """Place an urgent call to `to_number`. Returns the Twilio Call SID.

    Twilio fetches `/urgent_call_twiml` to learn what to play, POSTs
    to `/urgent_call_pressed?attempt_id=...` when Gather completes
    (digit or timeout), and POSTs lifecycle events to
    `/urgent_call_status?attempt_id=...`. The attempt_id query
    parameter is how the route handlers correlate the inbound
    Twilio callback to the orchestration row in Supabase.
    """
    if not config.TWILIO_FROM_NUMBER:
        raise RuntimeError("TWILIO_FROM_NUMBER must be set")

    twiml_url = _callback_url("/urgent_call_twiml", attempt_id)
    status_callback_url = _callback_url("/urgent_call_status", attempt_id)

    client = _twilio_client()
    call = client.calls.create(
        to=to_number,
        from_=config.TWILIO_FROM_NUMBER,
        url=twiml_url,
        method="GET",
        status_callback=status_callback_url,
        status_callback_method="POST",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )

    logger.info(
        "urgent_call placed: attempt_id=%s call_sid=%s to=%s",
        attempt_id,
        call.sid,
        to_number,
    )
    return call.sid


def generate_urgent_twiml(attempt_id: str) -> str:
    """Build the TwiML XML the urgent call should play.

    Gather captures one DTMF digit (or times out). The Gather action
    URL carries `attempt_id` as a query param so the digit handler
    can correlate the press to the Supabase row.
    """
    response = VoiceResponse()
    gather = Gather(
        num_digits=_GATHER_NUM_DIGITS,
        timeout=_GATHER_TIMEOUT_SECONDS,
        action=_callback_url("/urgent_call_pressed", attempt_id),
        method="POST",
    )
    gather.say(_URGENT_MESSAGE, voice=_VOICE)
    response.append(gather)
    # If Gather times out without a digit, Twilio falls through to
    # the next verb. Hang up rather than looping.
    response.hangup()
    return str(response)


def generate_thank_you_twiml() -> str:
    """TwiML played when Manny pressed a digit."""
    response = VoiceResponse()
    response.say(_THANK_YOU_MESSAGE, voice=_VOICE)
    response.hangup()
    return str(response)


def generate_no_digit_twiml() -> str:
    """TwiML played when Gather timed out without a digit press."""
    response = VoiceResponse()
    response.say(_NO_DIGIT_MESSAGE, voice=_VOICE)
    response.hangup()
    return str(response)
