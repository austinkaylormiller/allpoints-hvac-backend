"""ElevenLabs post-call webhook handling.

Receives ElevenLabs post-call webhook events (transcript + audio) and
forwards them to the Booker dashboard's Lovable edge function. Forked
verbatim from T&T HVAC (which itself was forked from Branded Barber's
production implementation). Replaces the Make.com dashboard scenario.

Forwarding is gated by config.POST_CALL_WEBHOOK_FORWARDING_ENABLED so
the TEST Railway service can accept and log webhooks without writing
to the production Booker dashboard.

This module is FastAPI-free per the services/ portability convention:
the api/ layer parses the request and passes a plain dict to
handle_webhook().
"""

import logging
import re
from typing import Any, Optional

import httpx

import config

logger = logging.getLogger(__name__)

# Forwarded to the Booker dashboard so the dashboard can attribute the
# call to the right organization alongside agent_id. AllPoints HVAC's
# row in the Supabase organizations table is keyed by agent_id
# agent_4301kd412wrefv7a9t8hc402fra3.
CLIENT_NAME = "AllPoints HVAC"

# Data-collection fields pulled from analysis.data_collection_results.
# Inherited verbatim from Branded Barber to keep the forwarded payload
# shape identical to what the (unchanged) Lovable edge function expects.
# Fields the AllPoints HVAC agent does not emit simply forward as null.
_OPTIONAL_FIELDS = (
    "caller_name",
    "caller_phone",
    "caller_reason",
    "service_requested",
    "barber_requested",
    "appointment_time",
    "unanswered_questions",
)

# Transcription events shorter than this are treated as noise (hang-ups,
# misdials) and dropped before forwarding — Branded Barber convention.
_MIN_DURATION_SECS = 20


def _clean_optional(value: Any) -> Optional[str]:
    """Return None for missing/empty/null/'N/A' values; otherwise the string."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "n/a"):
        return None
    return s


def _extract_data_collection(results: dict, field: str) -> Optional[str]:
    entry = results.get(field) or {}
    return _clean_optional(entry.get("value"))


async def _forward_to_booker(payload: dict) -> httpx.Response:
    """POST the payload to the Booker dashboard's Lovable edge function.

    Authenticates with a shared-secret header (x-webhook-secret) — the
    exact scheme the unchanged Lovable function already validates. No
    HMAC; matches Branded Barber's production implementation.
    """
    headers = {
        "Content-Type": "application/json",
        "x-webhook-secret": config.BOOKER_WEBHOOK_SECRET or "",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await client.post(
            config.BOOKER_WEBHOOK_URL, json=payload, headers=headers
        )


async def _maybe_forward(outbound: dict, kind: str, conversation_id: Any) -> dict:
    """Forward to the Booker dashboard unless forwarding is disabled.

    Never raises: a downstream failure is logged and swallowed so the
    endpoint can still return 200 to ElevenLabs.
    """
    if not config.POST_CALL_WEBHOOK_FORWARDING_ENABLED:
        logger.info(
            "elevenlabs_post_call accepted %s: conversation_id=%s "
            "did NOT forward (forwarding disabled)",
            kind,
            conversation_id,
        )
        return {"forwarded": False, "type": kind, "reason": "forwarding_disabled"}

    try:
        resp = await _forward_to_booker(outbound)
        logger.info(
            "elevenlabs_post_call forwarded %s: status=%s conversation_id=%s",
            kind,
            resp.status_code,
            conversation_id,
        )
        return {"forwarded": True, "type": kind, "status": resp.status_code}
    except Exception as e:
        logger.exception(
            "elevenlabs_post_call %s forward failed (conversation_id=%s)",
            kind,
            conversation_id,
        )
        return {"forwarded": False, "type": kind, "error": str(e)}


async def handle_webhook(body: dict) -> dict:
    """Route an ElevenLabs post-call webhook event by its type.

    Always returns a dict (HTTP 200 at the api/ layer) — unknown types
    and downstream failures are logged, never raised.
    """
    event_type = body.get("type")
    data = body.get("data") or {}
    conversation_id = data.get("conversation_id")
    logger.info(
        "elevenlabs_post_call entry: type=%s conversation_id=%s",
        event_type,
        conversation_id,
    )

    if event_type == "post_call_transcription":
        return await _handle_transcription(data, conversation_id)
    if event_type == "post_call_audio":
        return await _handle_audio(data, conversation_id)

    logger.info("elevenlabs_post_call skipped: unknown_type=%s", event_type)
    return {"skipped": True, "reason": "unknown_type", "type": event_type}


async def _handle_transcription(data: dict, conversation_id: Any) -> dict:
    metadata = data.get("metadata") or {}
    phone_call = metadata.get("phone_call") or {}

    duration_seconds = metadata.get("call_duration_secs")
    if duration_seconds is not None and duration_seconds <= _MIN_DURATION_SECS:
        logger.info(
            "elevenlabs_post_call skipped: duration_too_short "
            "(%ss, conversation_id=%s)",
            duration_seconds,
            conversation_id,
        )
        return {"skipped": True, "reason": "duration_too_short"}

    transcript_array = data.get("transcript") or []
    transcript = "".join(
        f"{turn.get('role', '')}: {turn.get('message', '')}\n"
        for turn in transcript_array
        if (turn.get("message") or "").strip()
    )

    analysis = data.get("analysis") or {}
    results = analysis.get("data_collection_results") or {}
    call_outcome = _extract_data_collection(results, "call_outcome") or "Incomplete"

    outbound: dict[str, Any] = {
        "agent_id": data.get("agent_id"),
        "conversation_id": conversation_id,
        "client_name": CLIENT_NAME,
        "transcript": transcript,
        "duration_seconds": duration_seconds,
        "call_outcome": call_outcome,
        "caller_email": None,
        "caller_address": None,
    }
    for field in _OPTIONAL_FIELDS:
        outbound[field] = _extract_data_collection(results, field)

    if outbound.get("caller_phone") is None:
        external_number = (phone_call.get("external_number") or "").strip()
        digits = re.sub(r"\D", "", external_number)
        if external_number and len(digits) >= 10:
            if external_number.startswith("+"):
                fallback = external_number
            elif len(digits) == 10:
                fallback = f"+1{digits}"
            else:
                logger.warning(
                    "caller_phone fallback unrecognized format: "
                    "conversation_id=%s digit_count=%d",
                    conversation_id,
                    len(digits),
                )
                fallback = external_number
            outbound["caller_phone"] = fallback
            logger.info(
                "caller_phone fallback applied: conversation_id=%s",
                conversation_id,
            )

    return await _maybe_forward(outbound, "transcription", conversation_id)


async def _handle_audio(data: dict, conversation_id: Any) -> dict:
    audio_b64_raw = data.get("full_audio") or ""
    if "base64," in audio_b64_raw:
        audio_b64 = audio_b64_raw.split("base64,", 1)[1]
    else:
        audio_b64 = audio_b64_raw
    audio_b64 = audio_b64.strip()

    logger.info(
        "elevenlabs_post_call audio: conversation_id=%s audio_b64 length=%d",
        conversation_id,
        len(audio_b64),
    )

    outbound = {
        "type": "post_call_audio",
        "conversation_id": conversation_id,
        "audio_b64": audio_b64,
    }
    return await _maybe_forward(outbound, "audio", conversation_id)
