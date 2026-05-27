"""Orchestration logic for /urgent_call.

Flow:
1. `handle_urgent_call` (called synchronously from the route):
   - Sends the initial urgent email.
   - Creates an urgent_call_attempts row in Supabase (status="pending").
   - Spawns `orchestrate_urgent_call(attempt_id)` as a background
     asyncio task.
   - Returns immediately with the attempt_id.
2. `orchestrate_urgent_call` (background task):
   - Up to 3 Twilio call attempts. After each call, sleeps the
     attempt timeout, then polls Supabase 3x at 1s intervals to
     catch a status flip from "calling" → "confirmed" that arrived
     just as the sleep ended.
   - If all 3 attempts time out, marks status="never_confirmed"
     and sends the failure email.
3. `handle_digit_pressed` (called from /urgent_call_pressed route):
   - Updates the row to status="confirmed", records digits, sends
     the confirmation email. Returns TwiML for Twilio.
4. `handle_call_status` (called from /urgent_call_status route):
   - Appends a Twilio lifecycle event to the call_attempts JSONB
     array. Observability only; does not drive control flow.

Background-task safety: every coroutine that runs detached from a
request wraps its body in try/except so an uncaught exception is
logged rather than disappearing into the event loop.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import config
from models.schemas import UrgentCallRequest
from services import email_send, supabase_client, twilio_client

logger = logging.getLogger(__name__)

# How many call attempts before giving up.
MAX_ATTEMPTS = 3

# Race-grace polling: after the sleep ends, check Supabase a few
# more times before treating the attempt as a failure. Catches a
# digit press that lands just after the sleep wakes up.
RACE_POLL_COUNT = 3
RACE_POLL_INTERVAL_SECONDS = 1


def _attempt_timeout_seconds() -> int:
    """Per-attempt sleep before the orchestration treats it as failed.

    Matches the Make.com 90s grace window: long enough for a Twilio
    call to ring out, go to voicemail, and resolve. No FAST_MODE
    override — integration tests must run against the real timing
    so the recipient experience is validated end-to-end.
    """
    return 90


def _between_attempts_seconds() -> int:
    """Sleep between attempt N and attempt N+1 (Make.com convention)."""
    return 30


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


async def handle_urgent_call(request: UrgentCallRequest) -> dict:
    """Synchronous entry: email + Supabase row + spawn the loop.

    Returns the API response shape immediately. The Twilio call
    placement happens inside the background task to keep the
    request short.
    """
    # The initial email is the most important side effect: even if
    # Twilio fails to dial, the office still has the urgent details.
    # Send it first so a Twilio outage cannot suppress the email.
    email_send.handle_urgent_initial_email(request)

    row = supabase_client.create_urgent_attempt(
        {
            "customer_name": request.customerName,
            "customer_phone": request.phone,
            "customer_address": request.address,
            "service_issue": request.serviceIssue,
        }
    )
    attempt_id = row["id"]

    asyncio.create_task(orchestrate_urgent_call(attempt_id))

    logger.info(
        "urgent_call dispatched: attempt_id=%s customer=%s",
        attempt_id,
        request.customerName,
    )
    return {
        "status": "ok",
        "message": (
            "Urgent dispatch initiated. The owner will be contacted immediately."
        ),
        "attempt_id": attempt_id,
    }


async def orchestrate_urgent_call(attempt_id: str) -> None:
    """3-attempt retry loop. Runs detached on the event loop."""
    try:
        await _orchestrate_inner(attempt_id)
    except Exception:
        logger.exception(
            "orchestrate_urgent_call: uncaught exception attempt_id=%s",
            attempt_id,
        )


async def _orchestrate_inner(attempt_id: str) -> None:
    if not config.URGENT_CALL_RECIPIENT_PHONE:
        logger.error(
            "orchestrate_urgent_call: URGENT_CALL_RECIPIENT_PHONE unset; "
            "aborting attempt_id=%s",
            attempt_id,
        )
        supabase_client.update_urgent_attempt(attempt_id, status="error")
        return

    for attempt_num in range(1, MAX_ATTEMPTS + 1):
        supabase_client.update_urgent_attempt(
            attempt_id, attempt_num=attempt_num, status="calling"
        )

        try:
            call_sid = twilio_client.create_urgent_call(
                to_number=config.URGENT_CALL_RECIPIENT_PHONE,
                attempt_id=attempt_id,
            )
        except Exception as e:
            logger.exception(
                "orchestrate_urgent_call: twilio create_call failed "
                "attempt_id=%s attempt_num=%d",
                attempt_id,
                attempt_num,
            )
            supabase_client.append_call_attempt_log(
                attempt_id,
                {
                    "attempt_num": attempt_num,
                    "outcome": "twilio_error",
                    "error": str(e),
                    "received_at": _utcnow_iso(),
                },
            )
            # Treat a Twilio placement failure like an attempt that
            # never connected: wait and retry on the next iteration.
            if attempt_num < MAX_ATTEMPTS:
                await asyncio.sleep(_between_attempts_seconds())
            continue

        supabase_client.update_urgent_attempt(attempt_id, last_call_sid=call_sid)
        supabase_client.append_call_attempt_log(
            attempt_id,
            {
                "attempt_num": attempt_num,
                "call_sid": call_sid,
                "outcome": "placed",
                "placed_at": _utcnow_iso(),
            },
        )

        await asyncio.sleep(_attempt_timeout_seconds())

        # Race-grace: a digit press could land just as the sleep
        # ends. Poll a few times before giving up on this attempt.
        confirmed = False
        for _ in range(RACE_POLL_COUNT):
            current = supabase_client.get_urgent_attempt_by_id(attempt_id)
            if current and current.get("status") == "confirmed":
                confirmed = True
                break
            await asyncio.sleep(RACE_POLL_INTERVAL_SECONDS)

        if confirmed:
            logger.info(
                "orchestrate_urgent_call: confirmed on attempt %d "
                "attempt_id=%s",
                attempt_num,
                attempt_id,
            )
            return

        if attempt_num < MAX_ATTEMPTS:
            await asyncio.sleep(_between_attempts_seconds())

    # All MAX_ATTEMPTS exhausted without a confirmation.
    supabase_client.update_urgent_attempt(attempt_id, status="never_confirmed")
    final = supabase_client.get_urgent_attempt_by_id(attempt_id)
    if final is None:
        logger.error(
            "orchestrate_urgent_call: row vanished before "
            "never-confirmed email attempt_id=%s",
            attempt_id,
        )
        return
    email_send.handle_urgent_never_confirmed_email(final, attempts_made=MAX_ATTEMPTS)
    logger.warning(
        "orchestrate_urgent_call: never_confirmed after %d attempts "
        "attempt_id=%s",
        MAX_ATTEMPTS,
        attempt_id,
    )


async def handle_digit_pressed(
    attempt_id: str, digits: Optional[str], call_sid: str
) -> str:
    """Twilio Gather action: digit pressed or Gather timed out.

    Returns the TwiML response Twilio should play before hanging up.
    """
    try:
        return await _digit_pressed_inner(attempt_id, digits, call_sid)
    except Exception:
        logger.exception(
            "handle_digit_pressed: uncaught attempt_id=%s call_sid=%s",
            attempt_id,
            call_sid,
        )
        # Twilio still needs valid TwiML so the call ends cleanly.
        return twilio_client.generate_no_digit_twiml()


async def _digit_pressed_inner(
    attempt_id: str, digits: Optional[str], call_sid: str
) -> str:
    if not digits:
        # Gather timed out — no digit press. Don't touch status; the
        # orchestration loop is what decides whether to retry.
        supabase_client.append_call_attempt_log(
            attempt_id,
            {
                "call_sid": call_sid,
                "outcome": "no_digit",
                "received_at": _utcnow_iso(),
            },
        )
        logger.info(
            "urgent_call digit handler: no digit attempt_id=%s call_sid=%s",
            attempt_id,
            call_sid,
        )
        return twilio_client.generate_no_digit_twiml()

    row = supabase_client.get_urgent_attempt_by_id(attempt_id)
    if row is None:
        logger.warning(
            "urgent_call digit handler: unknown attempt_id=%s call_sid=%s "
            "(returning thank-you anyway)",
            attempt_id,
            call_sid,
        )
        return twilio_client.generate_thank_you_twiml()

    confirmed_at = _utcnow_iso()
    supabase_client.update_urgent_attempt(
        attempt_id,
        status="confirmed",
        digits_pressed=digits,
        confirmed_at=confirmed_at,
    )
    supabase_client.append_call_attempt_log(
        attempt_id,
        {
            "call_sid": call_sid,
            "outcome": "confirmed",
            "digits_pressed": digits,
            "received_at": confirmed_at,
        },
    )

    # Re-read so the email has the latest snapshot (including the
    # status and confirmed_at fields).
    updated = supabase_client.get_urgent_attempt_by_id(attempt_id) or row
    email_send.handle_urgent_confirmation_email(updated, confirmed_at=confirmed_at)

    logger.info(
        "urgent_call confirmed: attempt_id=%s digits=%s call_sid=%s",
        attempt_id,
        digits,
        call_sid,
    )
    return twilio_client.generate_thank_you_twiml()


async def handle_call_status(
    attempt_id: str,
    call_sid: str,
    call_status: str,
    call_duration: Optional[str],
) -> None:
    """Twilio status callback: log only, no control-flow effects."""
    try:
        supabase_client.append_call_attempt_log(
            attempt_id,
            {
                "call_sid": call_sid,
                "twilio_status": call_status,
                "duration": call_duration,
                "received_at": _utcnow_iso(),
            },
        )
    except Exception:
        logger.exception(
            "handle_call_status: append_call_attempt_log failed "
            "attempt_id=%s call_sid=%s",
            attempt_id,
            call_sid,
        )
