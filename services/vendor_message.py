"""Vendor message handling logic.

Stub implementation writes to data/messages.jsonl; the real
implementation sends email via Resend. Behavior is controlled by
config.USE_STUB_VENDOR_MESSAGE.

Vendor messages are kept structurally identical to T&T HVAC — same
fields, same defensive parsing, same template, same response shape.
"""

import json
import logging
from datetime import datetime, timezone

import resend

import config
from models.schemas import VendorMessageRequest
from services import email_templates

logger = logging.getLogger(__name__)

_SUCCESS_MESSAGE = "Vendor message received. The office will follow up."


def handle_vendor_message(request: VendorMessageRequest) -> dict:
    """Process a vendor message and return a VendorMessageResponse dict."""
    if config.USE_STUB_VENDOR_MESSAGE:
        _stub_store(request)
    else:
        _send_via_resend(request)
    return {"status": "ok", "message": _SUCCESS_MESSAGE}


def _stub_store(request: VendorMessageRequest) -> None:
    """Append one vendor message as a JSON line to messages.jsonl."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "received_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "name": request.name,
        "company": request.company,
        "phone": request.phone,
        "reason": request.reason,
    }
    with open(config.MESSAGES_JSONL_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info(
        "vendor_message stored: name=%s company=%s phone=%s",
        request.name,
        request.company,
        request.phone,
    )


def _send_via_resend(request: VendorMessageRequest) -> None:
    if not config.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not set in environment")
    if not config.OFFICE_EMAIL_RECIPIENTS:
        raise RuntimeError("OFFICE_EMAIL_RECIPIENTS is not set in environment")

    resend.api_key = config.RESEND_API_KEY

    html_body = email_templates.vendor_message_html(
        name=request.name,
        company=request.company,
        phone=request.phone,
        reason=request.reason,
        client_business_name=config.CLIENT_BUSINESS_NAME,
    )
    text_body = email_templates.vendor_message_text(
        name=request.name,
        company=request.company,
        phone=request.phone,
        reason=request.reason,
        client_business_name=config.CLIENT_BUSINESS_NAME,
    )
    subject = f"Vendor Message - {request.company}"

    response = resend.Emails.send(
        {
            "from": config.FROM_EMAIL,
            "to": config.OFFICE_EMAIL_RECIPIENTS,
            "reply_to": "austin@getbookerai.com",
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }
    )

    logger.info(
        "vendor_message sent via Resend: id=%s to=%s company=%s",
        response["id"],
        config.OFFICE_EMAIL_RECIPIENTS,
        request.company,
    )
