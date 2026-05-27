"""Endpoint-level tests using FastAPI's TestClient.

Mirror of T&T HVAC's coverage, extended for the 2 Manny's Oil
endpoints and the email/callTimestamp optional fields. Tests run
against the stub implementation (for vendor_message) and against
mocked Resend (for the 7 branded-email endpoints).
"""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import config
from api.main import app
from services.utils import normalize_phone


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient on the stub path with storage redirected to a tmp path."""
    monkeypatch.setattr(config, "USE_STUB_VENDOR_MESSAGE", True)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "MESSAGES_JSONL_PATH", tmp_path / "messages.jsonl")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def real_client(monkeypatch):
    """TestClient on the real Resend path (the SDK call itself is mocked)."""
    monkeypatch.setattr(config, "USE_STUB_VENDOR_MESSAGE", False)
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_fake_test_key")
    monkeypatch.setattr(config, "OFFICE_EMAIL_RECIPIENTS", ["test@example.com"])
    monkeypatch.setattr(config, "CLIENT_BUSINESS_NAME", "AllPoints HVAC")
    monkeypatch.setattr(config, "MANNY_BUSINESS_NAME", "Manny's Oil Company")
    with TestClient(app) as test_client:
        yield test_client


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- /vendor_message (mirror T&T verbatim) ---


def test_vendor_message_happy_path(client):
    payload = {
        "name": "Marcus Webb",
        "company": "ACME Parts",
        "phone": "555-123-4567",
        "reason": "following up on invoice",
    }
    resp = client.post("/vendor_message", json=payload)
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "ok"
    assert body["message"] == "Vendor message received. The office will follow up."

    lines = config.MESSAGES_JSONL_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["received_at"]
    assert record["phone"] == "5551234567"


def test_vendor_message_missing_field_returns_422(client):
    payload = {
        "name": "Marcus Webb",
        "phone": "555-123-4567",
        "reason": "following up on invoice",
    }
    resp = client.post("/vendor_message", json=payload)
    assert resp.status_code == 422


def test_vendor_message_short_phone_returns_422(client):
    payload = {
        "name": "Bad",
        "company": "Nowhere Inc",
        "phone": "123",
        "reason": "test",
    }
    resp = client.post("/vendor_message", json=payload)
    assert resp.status_code == 422
    assert "phone" in resp.text.lower()


def test_vendor_message_accepts_spoken_word_phone(client):
    payload = {
        "name": "Marcus Webb",
        "company": "ACME Parts",
        "phone": "five-five-five, two-one-three, four-seven-eight-nine",
        "reason": "following up on invoice",
    }
    resp = client.post("/vendor_message", json=payload)
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "ok"

    lines = config.MESSAGES_JSONL_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["phone"] == "5552134789"


def test_vendor_message_real_resend_happy_path(real_client):
    payload = {
        "name": "Marcus Webb",
        "company": "ACME Parts",
        "phone": "(555) 123-4567",
        "reason": "following up on invoice",
    }
    with patch("services.vendor_message.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "test_message_id"}
        resp = real_client.post("/vendor_message", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"

    mock_send.assert_called_once()
    sent = mock_send.call_args.args[0]
    assert sent["from"] == config.FROM_EMAIL
    assert sent["to"] == ["test@example.com"]
    assert sent["subject"] == "Vendor Message - ACME Parts"
    assert "Marcus Webb" in sent["html"]
    assert "Marcus Webb" in sent["text"]
    assert sent["reply_to"] == "austin@getbookerai.com"


def test_vendor_message_resend_failure_returns_500(real_client):
    payload = {
        "name": "Marcus Webb",
        "company": "ACME Parts",
        "phone": "(555) 123-4567",
        "reason": "following up on invoice",
    }
    with patch("services.vendor_message.resend.Emails.send") as mock_send:
        mock_send.side_effect = Exception("Resend API error")
        resp = real_client.post("/vendor_message", json=payload)

    assert resp.status_code == 500
    body = resp.json()
    assert body["status"] == "error"
    assert body["message"] == (
        "Sorry, our message system is having an issue. "
        "Please call back later or email us directly."
    )


# --- 7 branded-email endpoints (5 AllPoints + 2 Manny's Oil) ---


EMAIL_ENDPOINT_CASES = [
    {
        "path": "/scheduling_email",
        "payload": {
            "customerName": "Jane Doe",
            "phone": "(555) 123-4567",
            "address": "12 Maple St, Worcester, MA",
            "serviceIssue": "Furnace not igniting",
            "preferredTimes": "Tuesday afternoon",
        },
        "expected_subject": "New Appointment Request - Jane Doe",
        "expected_header": "New Appointment Request",
        "expected_business": "AllPoints HVAC",
        "expected_body_contains": [
            "Jane Doe",
            "12 Maple St, Worcester, MA",
            "Furnace not igniting",
            "Tuesday afternoon",
        ],
        "expected_success_message": (
            "Appointment request received. The office will follow up to confirm."
        ),
    },
    {
        "path": "/reschedule_email",
        "payload": {
            "customerName": "John Smith",
            "phone": "(555) 222-3333",
            "originalAppointment": "Friday May 29 at 2pm",
            "preferredTimes": "Next Tuesday morning",
        },
        "expected_subject": "Appointment Reschedule Request - John Smith",
        "expected_header": "Appointment Reschedule Request",
        "expected_business": "AllPoints HVAC",
        "expected_body_contains": [
            "John Smith",
            "Friday May 29 at 2pm",
            "Next Tuesday morning",
        ],
        "expected_success_message": (
            "Reschedule request received. The office will follow up to confirm."
        ),
    },
    {
        "path": "/cancel_email",
        "payload": {
            "customerName": "Pat Lee",
            "phone": "(555) 444-5555",
            "appointmentToCancel": "Wednesday May 27 at 10am",
        },
        "expected_subject": "Appointment Cancellation Request - Pat Lee",
        "expected_header": "Appointment Cancellation Request",
        "expected_business": "AllPoints HVAC",
        "expected_body_contains": [
            "Pat Lee",
            "Wednesday May 27 at 10am",
        ],
        "expected_success_message": (
            "Cancellation request received. The office will follow up to confirm."
        ),
    },
    {
        "path": "/general_inquiries_email",
        "payload": {
            "customerName": "Sam Rivera",
            "phone": "(555) 666-7777",
            "inquiry": "Wants to ask about annual maintenance plans",
            "preferredTimes": "Anytime after 3pm",
        },
        "expected_subject": "Callback Request - Sam Rivera",
        "expected_header": "Callback Requested",
        "expected_business": "AllPoints HVAC",
        "expected_body_contains": [
            "Sam Rivera",
            "Wants to ask about annual maintenance plans",
            "Anytime after 3pm",
        ],
        "expected_success_message": (
            "Callback request received. The office will follow up."
        ),
    },
    {
        "path": "/recent_service_email",
        "payload": {
            "customerName": "Dana Park",
            "phone": "(555) 888-9999",
            "inquiry": "Furnace still making the same noise after Monday repair",
            "preferredTimes": "Tomorrow morning",
        },
        "expected_subject": "Recent Service Follow-up - Dana Park",
        "expected_header": "Recent Service Follow-up",
        "expected_business": "AllPoints HVAC",
        "expected_body_contains": [
            "Dana Park",
            "Furnace still making the same noise after Monday repair",
            "Tomorrow morning",
        ],
        "expected_success_message": (
            "Follow-up request received. The office will follow up."
        ),
    },
    {
        "path": "/manny_oil_delivery_request",
        "payload": {
            "customerName": "Maria Santos",
            "phone": "(508) 555-0890",
            "address": "45 Oak Ave, Worcester, MA",
            "preferredTimes": "Anytime this week",
        },
        "expected_subject": "Manny's Oil - Delivery Request - Maria Santos",
        "expected_header": "Oil Delivery Request",
        "expected_business": "Manny's Oil Company",
        "expected_body_contains": [
            "Maria Santos",
            "45 Oak Ave, Worcester, MA",
            "Anytime this week",
        ],
        "expected_success_message": (
            "Delivery request received. The office will follow up to confirm."
        ),
    },
    {
        "path": "/manny_oil_general_inquiries",
        "payload": {
            "customerName": "Robert Williams",
            "phone": "(508) 555-0911",
            "inquiry": "Question about my recent invoice",
            "preferredTimes": "Weekday mornings",
        },
        "expected_subject": "Callback Request, Manny's Oil - Robert Williams",
        "expected_header": "Callback Requested",
        "expected_business": "Manny's Oil Company",
        "expected_body_contains": [
            "Robert Williams",
            "Question about my recent invoice",
            "Weekday mornings",
        ],
        "expected_success_message": (
            "Callback request received. The office will follow up."
        ),
    },
]


@pytest.mark.parametrize("case", EMAIL_ENDPOINT_CASES, ids=lambda c: c["path"])
def test_branded_email_happy_path(real_client, case):
    with patch("services.email_send.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "test_message_id"}
        resp = real_client.post(case["path"], json=case["payload"])

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["message"] == case["expected_success_message"]

    mock_send.assert_called_once()
    sent = mock_send.call_args.args[0]
    assert sent["from"] == config.FROM_EMAIL
    assert sent["to"] == ["test@example.com"]
    assert sent["reply_to"] == "austin@getbookerai.com"
    assert sent["subject"] == case["expected_subject"]
    assert case["expected_header"] in sent["html"]
    assert case["expected_header"] in sent["text"]
    # HTML body escapes apostrophes; the plain-text body keeps them raw.
    # Verify the brand renders in both forms.
    assert case["expected_business"] in sent["text"]
    import html as _html
    assert _html.escape(case["expected_business"]) in sent["html"]
    for needle in case["expected_body_contains"]:
        assert needle in sent["html"], f"missing in html: {needle!r}"
        assert needle in sent["text"], f"missing in text: {needle!r}"


@pytest.mark.parametrize("case", EMAIL_ENDPOINT_CASES, ids=lambda c: c["path"])
def test_branded_email_normalizes_spoken_phone(real_client, case):
    payload = dict(case["payload"])
    payload["phone"] = (
        "five-five-five, two-one-three, four-seven-eight-nine"
    )
    with patch("services.email_send.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "test_message_id"}
        resp = real_client.post(case["path"], json=payload)

    assert resp.status_code == 200, resp.text
    sent = mock_send.call_args.args[0]
    assert "555-213-4789" in sent["html"]
    assert "555-213-4789" in sent["text"]


@pytest.mark.parametrize("case", EMAIL_ENDPOINT_CASES, ids=lambda c: c["path"])
def test_branded_email_missing_field_returns_422(real_client, case):
    payload = dict(case["payload"])
    payload.pop(list(payload.keys())[-1])
    resp = real_client.post(case["path"], json=payload)
    assert resp.status_code == 422


@pytest.mark.parametrize("case", EMAIL_ENDPOINT_CASES, ids=lambda c: c["path"])
def test_branded_email_optional_email_renders_when_present(real_client, case):
    payload = dict(case["payload"])
    payload["email"] = "caller@example.com"
    with patch("services.email_send.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "test_message_id"}
        resp = real_client.post(case["path"], json=payload)

    assert resp.status_code == 200, resp.text
    sent = mock_send.call_args.args[0]
    assert "caller@example.com" in sent["html"]
    assert "caller@example.com" in sent["text"]


@pytest.mark.parametrize("case", EMAIL_ENDPOINT_CASES, ids=lambda c: c["path"])
def test_branded_email_optional_email_absent_does_not_render_label(real_client, case):
    with patch("services.email_send.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "test_message_id"}
        resp = real_client.post(case["path"], json=case["payload"])

    assert resp.status_code == 200, resp.text
    sent = mock_send.call_args.args[0]
    # The "Email:" label only appears when email is supplied. Allow
    # incidental occurrences only if the substring appears elsewhere
    # in the template (it does not in our templates).
    assert "Email:" not in sent["text"]


@pytest.mark.parametrize("case", EMAIL_ENDPOINT_CASES, ids=lambda c: c["path"])
def test_branded_email_uses_provided_call_timestamp(real_client, case):
    provided_ts = "2026-05-27T14:23:00+00:00"
    payload = dict(case["payload"])
    payload["callTimestamp"] = provided_ts
    with patch("services.email_send.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "test_message_id"}
        resp = real_client.post(case["path"], json=payload)

    assert resp.status_code == 200, resp.text
    sent = mock_send.call_args.args[0]
    assert provided_ts in sent["html"]
    assert provided_ts in sent["text"]


@pytest.mark.parametrize("case", EMAIL_ENDPOINT_CASES, ids=lambda c: c["path"])
def test_branded_email_fills_call_timestamp_when_omitted(real_client, case):
    with patch("services.email_send.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "test_message_id"}
        resp = real_client.post(case["path"], json=case["payload"])

    assert resp.status_code == 200, resp.text
    sent = mock_send.call_args.args[0]
    # Server-filled fallback is a UTC ISO 8601 timestamp; check the
    # label is present in both renderings.
    assert "Call received:" in sent["text"]
    assert "Call received:" in sent["html"]


def test_general_inquiries_email_requires_lowercase_inquiry(real_client):
    """Capital `Inquiry` (the Make.com field name) must fail Pydantic validation."""
    payload = {
        "customerName": "Sam Rivera",
        "phone": "(555) 666-7777",
        "Inquiry": "Wants to ask about service area coverage",
        "preferredTimes": "Anytime after 3pm",
    }
    resp = real_client.post("/general_inquiries_email", json=payload)
    assert resp.status_code == 422


def test_manny_oil_general_requires_lowercase_inquiry(real_client):
    payload = {
        "customerName": "Robert Williams",
        "phone": "(508) 555-0911",
        "Inquiry": "Question about my recent invoice",
        "preferredTimes": "Weekday mornings",
    }
    resp = real_client.post("/manny_oil_general_inquiries", json=payload)
    assert resp.status_code == 422


# --- normalize_phone defensive paths ---


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("555-1234", "5551234"),
        ("(555) 123-4567", "5551234567"),
        ("+1 555 123 4567", "5551234567"),
        ("1-800-555-1234", "8005551234"),
        ("five-five-five, two-one-three, four-seven-eight-nine", "5552134789"),
        ("FIVE FIVE FIVE one two three four", "5551234"),
        ("oh-one-two-three-four-five-six", "0123456"),
        ("no number", ""),
        ("", ""),
        ("   ", ""),
        # Mixed digits + spoken words (caller correcting themselves).
        ("555 one two three 4567", "5551234567"),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


# --- /elevenlabs_post_call ---

WEBHOOK_URL = "https://lovable.test/functions/v1/elevenlabs-webhook"

TRANSCRIPT_PAYLOAD = {
    "type": "post_call_transcription",
    "data": {
        "agent_id": "agent_4301kd412wrefv7a9t8hc402fra3",
        "conversation_id": "conv_test_transcript",
        "metadata": {
            "call_duration_secs": 120,
            "phone_call": {"external_number": "+15551234567"},
        },
        "transcript": [
            {"role": "agent", "message": "This is Jason with AllPoints HVAC."},
            {"role": "user", "message": "My furnace stopped working."},
        ],
        "analysis": {
            "data_collection_results": {
                "call_outcome": {"value": "Service Booked"},
                "caller_name": {"value": "Jane Doe"},
                "caller_reason": {"value": "furnace not heating"},
            }
        },
    },
}

AUDIO_PAYLOAD = {
    "type": "post_call_audio",
    "data": {
        "conversation_id": "conv_test_audio",
        "full_audio": base64.b64encode(b"fake-call-recording-bytes").decode(),
    },
}


def _mock_async_client(*, status_code=200, error=None):
    cli = MagicMock()
    cli.__aenter__ = AsyncMock(return_value=cli)
    cli.__aexit__ = AsyncMock(return_value=False)
    if error is not None:
        cli.post = AsyncMock(side_effect=error)
    else:
        cli.post = AsyncMock(return_value=SimpleNamespace(status_code=status_code))
    return cli


def _set_webhook_config(monkeypatch, *, forwarding):
    monkeypatch.setattr(config, "BOOKER_WEBHOOK_URL", WEBHOOK_URL)
    monkeypatch.setattr(config, "BOOKER_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(config, "POST_CALL_WEBHOOK_FORWARDING_ENABLED", forwarding)


def test_elevenlabs_post_call_accepts_transcript_event(monkeypatch):
    _set_webhook_config(monkeypatch, forwarding=True)
    fake = _mock_async_client(status_code=200)
    with patch("services.elevenlabs_webhook.httpx.AsyncClient", return_value=fake):
        with TestClient(app) as c:
            resp = c.post("/elevenlabs_post_call", json=TRANSCRIPT_PAYLOAD)

    assert resp.status_code == 200
    fake.post.assert_called_once()
    call = fake.post.call_args
    assert call.args[0] == WEBHOOK_URL
    sent = call.kwargs["json"]
    assert sent["conversation_id"] == "conv_test_transcript"
    assert sent["client_name"] == "AllPoints HVAC"
    assert "furnace" in sent["transcript"]
    assert sent["caller_name"] == "Jane Doe"
    assert call.kwargs["headers"]["x-webhook-secret"] == "test-secret"

    _set_webhook_config(monkeypatch, forwarding=False)
    fake_off = _mock_async_client(status_code=200)
    with patch("services.elevenlabs_webhook.httpx.AsyncClient", return_value=fake_off):
        with TestClient(app) as c:
            resp = c.post("/elevenlabs_post_call", json=TRANSCRIPT_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["forwarded"] is False
    fake_off.post.assert_not_called()


def test_elevenlabs_post_call_accepts_audio_event(monkeypatch):
    _set_webhook_config(monkeypatch, forwarding=True)
    fake = _mock_async_client(status_code=200)
    with patch("services.elevenlabs_webhook.httpx.AsyncClient", return_value=fake):
        with TestClient(app) as c:
            resp = c.post("/elevenlabs_post_call", json=AUDIO_PAYLOAD)

    assert resp.status_code == 200
    fake.post.assert_called_once()
    sent = fake.post.call_args.kwargs["json"]
    assert sent["type"] == "post_call_audio"
    assert sent["conversation_id"] == "conv_test_audio"
    assert sent["audio_b64"] == AUDIO_PAYLOAD["data"]["full_audio"]

    _set_webhook_config(monkeypatch, forwarding=False)
    fake_off = _mock_async_client(status_code=200)
    with patch("services.elevenlabs_webhook.httpx.AsyncClient", return_value=fake_off):
        with TestClient(app) as c:
            resp = c.post("/elevenlabs_post_call", json=AUDIO_PAYLOAD)

    assert resp.status_code == 200
    fake_off.post.assert_not_called()


def test_elevenlabs_post_call_returns_200_even_if_lovable_fails(monkeypatch):
    _set_webhook_config(monkeypatch, forwarding=True)
    fake = _mock_async_client(error=RuntimeError("simulated Lovable outage"))
    with patch("services.elevenlabs_webhook.httpx.AsyncClient", return_value=fake):
        with TestClient(app) as c:
            resp = c.post("/elevenlabs_post_call", json=TRANSCRIPT_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["forwarded"] is False
