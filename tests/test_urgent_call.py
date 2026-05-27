"""Tests for the urgent_call orchestration.

Mocking strategy:
- `services.supabase_client.*` functions are mocked at the module
  boundary. The test owns a tiny in-memory store so the
  orchestration sees consistent reads.
- `services.twilio_client.create_urgent_call` is mocked to return a
  fake Call SID without ever hitting Twilio.
- `services.urgent_call.asyncio.sleep` is mocked to no-op so the
  orchestration loop runs in instant time even with 90s/30s
  configured.
- `services.email_send.resend.Emails.send` is mocked for the email
  paths.
"""

import asyncio
import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import config
from api.main import app


@pytest.fixture
def store():
    """In-memory stand-in for the urgent_call_attempts table.

    Each row is keyed by its UUID. The mocked supabase_client
    functions below read/write this dict so the orchestration sees
    a stable view of the row.
    """
    return {}


@pytest.fixture
def patched_env(monkeypatch):
    """Set the env vars urgent_call needs without touching the real ones."""
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_fake_test_key")
    monkeypatch.setattr(config, "OFFICE_EMAIL_RECIPIENTS", ["test@example.com"])
    monkeypatch.setattr(config, "CLIENT_BUSINESS_NAME", "AllPoints HVAC")
    monkeypatch.setattr(config, "MANNY_BUSINESS_NAME", "Manny's Oil Company")
    monkeypatch.setattr(config, "URGENT_CALL_RECIPIENT_PHONE", "+12065364398")
    monkeypatch.setattr(config, "URGENT_CALL_FAST_MODE", True)
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setattr(config, "TWILIO_ACCOUNT_SID", "AC_fake")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "fake_token")
    monkeypatch.setattr(config, "TWILIO_FROM_NUMBER", "+15084655351")


@pytest.fixture
def supabase_mocks(store, monkeypatch):
    """Patch the supabase_client functions with in-memory stand-ins."""
    next_id = {"n": 0}

    def _new_id() -> str:
        next_id["n"] += 1
        return f"attempt-{next_id['n']:04d}"

    def create_urgent_attempt(payload):
        row = {
            "id": _new_id(),
            "client_id": "allpoints-hvac",
            "status": "pending",
            "attempt_num": 0,
            "last_call_sid": None,
            "digits_pressed": None,
            "confirmed_at": None,
            "call_attempts": [],
            **{
                "customer_name": payload["customer_name"],
                "customer_phone": payload["customer_phone"],
                "customer_address": payload["customer_address"],
                "service_issue": payload["service_issue"],
            },
        }
        store[row["id"]] = row
        return dict(row)

    def update_urgent_attempt(attempt_id, **fields):
        if attempt_id not in store:
            raise RuntimeError(f"unknown attempt_id {attempt_id}")
        store[attempt_id].update(fields)
        return dict(store[attempt_id])

    def get_urgent_attempt_by_id(attempt_id):
        row = store.get(attempt_id)
        return dict(row) if row else None

    def get_urgent_attempt_by_call_sid(call_sid):
        for row in store.values():
            if row.get("last_call_sid") == call_sid:
                return dict(row)
        return None

    def append_call_attempt_log(attempt_id, entry):
        if attempt_id not in store:
            return
        store[attempt_id]["call_attempts"].append(entry)

    monkeypatch.setattr(
        "services.supabase_client.create_urgent_attempt",
        create_urgent_attempt,
    )
    monkeypatch.setattr(
        "services.supabase_client.update_urgent_attempt",
        update_urgent_attempt,
    )
    monkeypatch.setattr(
        "services.supabase_client.get_urgent_attempt_by_id",
        get_urgent_attempt_by_id,
    )
    monkeypatch.setattr(
        "services.supabase_client.get_urgent_attempt_by_call_sid",
        get_urgent_attempt_by_call_sid,
    )
    monkeypatch.setattr(
        "services.supabase_client.append_call_attempt_log",
        append_call_attempt_log,
    )
    return store


@pytest.fixture
def fast_sleep(monkeypatch):
    """No-op asyncio.sleep so orchestration runs in zero wall time."""

    async def _noop(seconds):
        return None

    monkeypatch.setattr("services.urgent_call.asyncio.sleep", _noop)


# --- /urgent_call request-handling tests ---


def test_urgent_call_happy_path_creates_row_and_spawns_task(
    patched_env, supabase_mocks, fast_sleep
):
    """Valid payload → 200 + attempt_id, initial email sent, row created,
    background task spawned. Orchestration runs but we don't care
    what it does here (covered separately)."""
    payload = {
        "customerName": "Jane Doe",
        "phone": "(508) 555-0147",
        "address": "12 Maple St, Worcester, MA",
        "serviceIssue": "No heat, furnace not igniting",
    }
    with patch("services.email_send.resend.Emails.send") as mock_send, patch(
        "services.urgent_call.twilio_client.create_urgent_call",
        return_value="CA_fake_sid",
    ):
        with TestClient(app) as client:
            resp = client.post("/urgent_call", json=payload)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["message"].startswith("Urgent dispatch initiated")
    assert body["attempt_id"]

    # Initial urgent email was attempted (subject starts with URGENT)
    initial_call = mock_send.call_args_list[0]
    sent = initial_call.args[0]
    assert sent["subject"] == "URGENT - Jane Doe"
    assert "Jane Doe" in sent["html"]
    assert "12 Maple St, Worcester, MA" in sent["html"]
    assert "No heat, furnace not igniting" in sent["html"]

    # The Supabase row exists and carries the normalized phone.
    attempt_id = body["attempt_id"]
    assert attempt_id in supabase_mocks
    row = supabase_mocks[attempt_id]
    assert row["customer_phone"] == "5085550147"


def test_urgent_call_missing_required_field_returns_422(patched_env):
    payload = {
        "customerName": "Jane Doe",
        "phone": "(508) 555-0147",
        "address": "12 Maple St",
        # serviceIssue intentionally omitted
    }
    with TestClient(app) as client:
        resp = client.post("/urgent_call", json=payload)
    assert resp.status_code == 422
    assert "serviceIssue" in resp.text


def test_urgent_call_invalid_phone_returns_422(patched_env):
    payload = {
        "customerName": "Jane Doe",
        "phone": "abc",
        "address": "12 Maple St",
        "serviceIssue": "No heat",
    }
    with TestClient(app) as client:
        resp = client.post("/urgent_call", json=payload)
    assert resp.status_code == 422
    assert "phone" in resp.text.lower()


# --- /urgent_call_pressed (Twilio Gather action) ---


def _seed_attempt(store, **overrides) -> str:
    row = {
        "id": "attempt-pre",
        "client_id": "allpoints-hvac",
        "status": "calling",
        "attempt_num": 1,
        "last_call_sid": "CA_seed",
        "digits_pressed": None,
        "confirmed_at": None,
        "call_attempts": [],
        "customer_name": "Jane Doe",
        "customer_phone": "5085550147",
        "customer_address": "12 Maple St",
        "service_issue": "No heat",
    }
    row.update(overrides)
    store[row["id"]] = row
    return row["id"]


def test_urgent_call_pressed_with_digit_confirms_and_emails(
    patched_env, supabase_mocks
):
    attempt_id = _seed_attempt(supabase_mocks)
    with patch("services.email_send.resend.Emails.send") as mock_send:
        with TestClient(app) as client:
            resp = client.post(
                f"/urgent_call_pressed?attempt_id={attempt_id}",
                data={"Digits": "5", "CallSid": "CA_pressed"},
            )

    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "Thank you, confirmation received." in resp.text
    assert "<Hangup" in resp.text

    row = supabase_mocks[attempt_id]
    assert row["status"] == "confirmed"
    assert row["digits_pressed"] == "5"
    assert row["confirmed_at"]
    log_outcomes = [entry.get("outcome") for entry in row["call_attempts"]]
    assert "confirmed" in log_outcomes

    sent = mock_send.call_args.args[0]
    assert sent["subject"] == "Urgent Confirmed - Jane Doe"
    assert "Jane Doe" in sent["html"]
    assert "Confirmed At" in sent["html"]


def test_urgent_call_pressed_with_empty_digits_no_confirm(
    patched_env, supabase_mocks
):
    attempt_id = _seed_attempt(supabase_mocks)
    with patch("services.email_send.resend.Emails.send") as mock_send:
        with TestClient(app) as client:
            resp = client.post(
                f"/urgent_call_pressed?attempt_id={attempt_id}",
                data={"Digits": "", "CallSid": "CA_no_digit"},
            )

    assert resp.status_code == 200
    assert "<Hangup" in resp.text
    # No confirmation email when no digit pressed.
    mock_send.assert_not_called()

    row = supabase_mocks[attempt_id]
    # Status untouched — orchestration loop owns retry decisions.
    assert row["status"] == "calling"
    assert row["digits_pressed"] is None
    log_outcomes = [entry.get("outcome") for entry in row["call_attempts"]]
    assert "no_digit" in log_outcomes


def test_urgent_call_pressed_unknown_attempt_id_returns_twiml(
    patched_env, supabase_mocks
):
    with patch("services.email_send.resend.Emails.send"):
        with TestClient(app) as client:
            resp = client.post(
                "/urgent_call_pressed?attempt_id=never-existed",
                data={"Digits": "5", "CallSid": "CA_ghost"},
            )

    assert resp.status_code == 200
    # Even with an unknown attempt_id we hand Twilio a clean response
    # so the call ends gracefully.
    assert "<Hangup" in resp.text


# --- /urgent_call_status (Twilio lifecycle callback) ---


def test_urgent_call_status_appends_log_and_returns_204(
    patched_env, supabase_mocks
):
    attempt_id = _seed_attempt(supabase_mocks)
    with TestClient(app) as client:
        resp = client.post(
            f"/urgent_call_status?attempt_id={attempt_id}",
            data={
                "CallSid": "CA_seed",
                "CallStatus": "completed",
                "CallDuration": "27",
            },
        )

    assert resp.status_code == 204
    row = supabase_mocks[attempt_id]
    statuses = [entry.get("twilio_status") for entry in row["call_attempts"]]
    assert "completed" in statuses
    # Control state was NOT touched.
    assert row["status"] == "calling"


# --- /urgent_call_twiml (Twilio TwiML fetch) ---


def test_urgent_call_twiml_returns_gather_and_message(patched_env):
    with TestClient(app) as client:
        resp = client.get("/urgent_call_twiml?attempt_id=attempt-xyz")

    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    body = resp.text
    assert "This is an urgent notification from AllPoints HVAC." in body
    assert "<Gather" in body
    assert 'numDigits="1"' in body
    assert 'timeout="15"' in body
    # The Gather action URL carries the attempt_id through.
    assert "attempt_id=attempt-xyz" in body


# --- Orchestration loop (the heart of the feature) ---


def test_orchestration_confirmed_on_attempt_1_no_failure_email(
    patched_env, supabase_mocks, fast_sleep
):
    """When the digit handler flips status to confirmed mid-loop,
    orchestration exits without placing further calls and without
    sending the never-confirmed email."""
    from services.urgent_call import orchestrate_urgent_call

    # Seed a row in pending state, the way handle_urgent_call would.
    from services.supabase_client import create_urgent_attempt
    row = create_urgent_attempt(
        {
            "customer_name": "Jane Doe",
            "customer_phone": "5085550147",
            "customer_address": "12 Maple St",
            "service_issue": "No heat",
        }
    )
    attempt_id = row["id"]

    sid_counter = {"n": 0}

    def fake_create_call(to_number, attempt_id):
        sid_counter["n"] += 1
        # Simulate the digit handler arriving during the post-call sleep:
        # flip the status to confirmed so the race-grace poll sees it.
        supabase_mocks[attempt_id]["status"] = "confirmed"
        return f"CA_call_{sid_counter['n']}"

    with patch(
        "services.urgent_call.twilio_client.create_urgent_call",
        side_effect=fake_create_call,
    ), patch("services.email_send.resend.Emails.send") as mock_send:
        asyncio.run(orchestrate_urgent_call(attempt_id))

    # Exactly one Twilio call placed.
    assert sid_counter["n"] == 1
    # No never-confirmed email.
    subjects = [c.args[0]["subject"] for c in mock_send.call_args_list]
    assert not any("All Phone Attempts Failed" in s for s in subjects)
    # Status remains confirmed.
    assert supabase_mocks[attempt_id]["status"] == "confirmed"


def test_orchestration_never_confirmed_sends_failure_email(
    patched_env, supabase_mocks, fast_sleep
):
    """3 attempts, nobody picks up — status flips to never_confirmed
    and the failure email goes out."""
    from services.urgent_call import orchestrate_urgent_call
    from services.supabase_client import create_urgent_attempt

    row = create_urgent_attempt(
        {
            "customer_name": "Jane Doe",
            "customer_phone": "5085550147",
            "customer_address": "12 Maple St",
            "service_issue": "No heat",
        }
    )
    attempt_id = row["id"]

    sid_counter = {"n": 0}

    def fake_create_call(to_number, attempt_id):
        sid_counter["n"] += 1
        return f"CA_call_{sid_counter['n']}"

    with patch(
        "services.urgent_call.twilio_client.create_urgent_call",
        side_effect=fake_create_call,
    ), patch("services.email_send.resend.Emails.send") as mock_send:
        asyncio.run(orchestrate_urgent_call(attempt_id))

    assert sid_counter["n"] == 3
    assert supabase_mocks[attempt_id]["status"] == "never_confirmed"
    subjects = [c.args[0]["subject"] for c in mock_send.call_args_list]
    assert any(
        s == "URGENT - All Phone Attempts Failed - Jane Doe" for s in subjects
    )


def test_orchestration_race_grace_catches_late_digit(
    patched_env, supabase_mocks, monkeypatch
):
    """Digit press lands during the race-grace polling window
    (between sleep end and the third poll). Orchestration should
    detect the flip and exit without placing attempt 2."""
    from services.urgent_call import orchestrate_urgent_call
    from services.supabase_client import create_urgent_attempt

    row = create_urgent_attempt(
        {
            "customer_name": "Jane Doe",
            "customer_phone": "5085550147",
            "customer_address": "12 Maple St",
            "service_issue": "No heat",
        }
    )
    attempt_id = row["id"]

    sid_counter = {"n": 0}

    def fake_create_call(to_number, attempt_id):
        sid_counter["n"] += 1
        return f"CA_call_{sid_counter['n']}"

    # Custom asyncio.sleep that flips status to confirmed on the
    # 3rd invocation (matching: attempt sleep, then race-grace
    # poll sleep #1 = no-op, race-grace poll sleep #2 = flip).
    sleep_calls = {"n": 0}

    async def staged_sleep(seconds):
        sleep_calls["n"] += 1
        if sleep_calls["n"] == 2:
            supabase_mocks[attempt_id]["status"] = "confirmed"

    monkeypatch.setattr("services.urgent_call.asyncio.sleep", staged_sleep)

    with patch(
        "services.urgent_call.twilio_client.create_urgent_call",
        side_effect=fake_create_call,
    ), patch("services.email_send.resend.Emails.send") as mock_send:
        asyncio.run(orchestrate_urgent_call(attempt_id))

    # Only attempt 1 should have been placed.
    assert sid_counter["n"] == 1
    # No failure email.
    subjects = [c.args[0]["subject"] for c in mock_send.call_args_list]
    assert not any("All Phone Attempts Failed" in s for s in subjects)


def test_orchestration_twilio_failure_appends_log_and_retries(
    patched_env, supabase_mocks, fast_sleep
):
    """If the Twilio SDK raises, that attempt logs a twilio_error
    entry and the loop moves on to the next attempt."""
    from services.urgent_call import orchestrate_urgent_call
    from services.supabase_client import create_urgent_attempt

    row = create_urgent_attempt(
        {
            "customer_name": "Jane Doe",
            "customer_phone": "5085550147",
            "customer_address": "12 Maple St",
            "service_issue": "No heat",
        }
    )
    attempt_id = row["id"]

    call_attempts = {"n": 0}

    def flaky_create_call(to_number, attempt_id):
        call_attempts["n"] += 1
        if call_attempts["n"] == 1:
            raise RuntimeError("simulated twilio error")
        return f"CA_call_{call_attempts['n']}"

    with patch(
        "services.urgent_call.twilio_client.create_urgent_call",
        side_effect=flaky_create_call,
    ), patch("services.email_send.resend.Emails.send"):
        asyncio.run(orchestrate_urgent_call(attempt_id))

    # First attempt raised; the loop retried twice more before giving up.
    assert call_attempts["n"] == 3
    outcomes = [
        entry.get("outcome") for entry in supabase_mocks[attempt_id]["call_attempts"]
    ]
    assert "twilio_error" in outcomes
