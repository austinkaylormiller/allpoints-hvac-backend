"""FastAPI app and route definitions.

Thin HTTP wrapper over services/. Keep this file free of business
logic — it should only define routes, call into services/, fill in
defaults at the request boundary, and shape responses.

callTimestamp default: when the agent did not send one (ElevenLabs
system value `{{system__time_utc}}`), we fill it in with the server's
current UTC time as an ISO 8601 string before the handler runs.
"""

import json
import logging
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import iterate_in_threadpool

from models.schemas import (
    CancelEmailRequest,
    GeneralInquiriesEmailRequest,
    MannyOilDeliveryRequestRequest,
    MannyOilGeneralInquiriesRequest,
    RecentServiceEmailRequest,
    RescheduleEmailRequest,
    SchedulingEmailRequest,
    VendorMessageErrorResponse,
    VendorMessageRequest,
)
from services.elevenlabs_webhook import handle_webhook
from services.email_send import (
    handle_cancel_email,
    handle_general_inquiries_email,
    handle_manny_oil_delivery_request,
    handle_manny_oil_general_inquiries,
    handle_recent_service_email,
    handle_reschedule_email,
    handle_scheduling_email,
)
from services.vendor_message import handle_vendor_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AllPoints HVAC Backend",
    version="0.1.0",
    description="Webhook endpoints for the AllPoints HVAC ElevenLabs voice agent (AllPoints HVAC + Manny's Oil Company).",
)

_ERROR_MESSAGE = (
    "Sorry, our message system is having an issue. "
    "Please call back later or email us directly."
)

# Cap how much of a request body we log. The /elevenlabs_post_call
# audio event carries the full call recording as base64 (multiple MB) —
# logging it whole would flood Railway.
_MAX_LOGGED_BODY = 2000


def _ensure_call_timestamp(request) -> None:
    """Fill request.callTimestamp with server UTC if the agent omitted it."""
    if request.callTimestamp is None:
        request.callTimestamp = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request/response pair per the CLAUDE.md convention."""
    start = time.perf_counter()
    endpoint = request.url.path

    raw_body = await request.body()

    async def _replay_receive() -> dict:
        return {"type": "http.request", "body": raw_body, "more_body": False}

    request._receive = _replay_receive

    content_type = request.headers.get("content-type", "")
    if not raw_body:
        req_repr = {}
    elif "application/json" in content_type:
        try:
            req_repr = json.loads(raw_body)
        except json.JSONDecodeError:
            req_repr = "<non-json body>"
    else:
        req_repr = "<non-json body>"

    req_log = repr(req_repr)
    if len(req_log) > _MAX_LOGGED_BODY:
        req_log = (
            f"{req_log[:_MAX_LOGGED_BODY]}...<truncated, {len(req_log)} chars total>"
        )
    logger.info("[%s] req=%s", endpoint, req_log)

    response = await call_next(request)

    body_chunks = [section async for section in response.body_iterator]
    response.body_iterator = iterate_in_threadpool(iter(body_chunks))
    resp_bytes = b"".join(body_chunks)
    try:
        resp_repr = json.loads(resp_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        resp_repr = resp_bytes.decode("utf-8", errors="replace")

    dur_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "[%s] resp_status=%s resp=%s dur=%.0fms",
        endpoint,
        response.status_code,
        resp_repr,
        dur_ms,
    )
    return response


@app.get("/health")
async def health() -> dict:
    """Liveness probe for Railway health checks and manual verification."""
    return {"status": "ok"}


@app.post("/vendor_message")
async def vendor_message(request: VendorMessageRequest):
    """Accept a vendor message from the agent's take_vendor_message node."""
    try:
        return handle_vendor_message(request)
    except Exception:
        logger.exception("vendor_message handler failed")
        error = VendorMessageErrorResponse(status="error", message=_ERROR_MESSAGE)
        return JSONResponse(status_code=500, content=error.model_dump())


@app.post("/scheduling_email")
async def scheduling_email(request: SchedulingEmailRequest):
    """Accept a new-appointment request from the AllPoints HVAC agent."""
    _ensure_call_timestamp(request)
    try:
        return handle_scheduling_email(request)
    except Exception:
        logger.exception("scheduling_email handler failed")
        error = VendorMessageErrorResponse(status="error", message=_ERROR_MESSAGE)
        return JSONResponse(status_code=500, content=error.model_dump())


@app.post("/reschedule_email")
async def reschedule_email(request: RescheduleEmailRequest):
    """Accept an appointment-reschedule request from the AllPoints HVAC agent."""
    _ensure_call_timestamp(request)
    try:
        return handle_reschedule_email(request)
    except Exception:
        logger.exception("reschedule_email handler failed")
        error = VendorMessageErrorResponse(status="error", message=_ERROR_MESSAGE)
        return JSONResponse(status_code=500, content=error.model_dump())


@app.post("/cancel_email")
async def cancel_email(request: CancelEmailRequest):
    """Accept an appointment-cancellation request from the AllPoints HVAC agent."""
    _ensure_call_timestamp(request)
    try:
        return handle_cancel_email(request)
    except Exception:
        logger.exception("cancel_email handler failed")
        error = VendorMessageErrorResponse(status="error", message=_ERROR_MESSAGE)
        return JSONResponse(status_code=500, content=error.model_dump())


@app.post("/general_inquiries_email")
async def general_inquiries_email(request: GeneralInquiriesEmailRequest):
    """Accept a general callback request from the AllPoints HVAC agent."""
    _ensure_call_timestamp(request)
    try:
        return handle_general_inquiries_email(request)
    except Exception:
        logger.exception("general_inquiries_email handler failed")
        error = VendorMessageErrorResponse(status="error", message=_ERROR_MESSAGE)
        return JSONResponse(status_code=500, content=error.model_dump())


@app.post("/recent_service_email")
async def recent_service_email(request: RecentServiceEmailRequest):
    """Accept a recent-service follow-up callback request from the AllPoints HVAC agent."""
    _ensure_call_timestamp(request)
    try:
        return handle_recent_service_email(request)
    except Exception:
        logger.exception("recent_service_email handler failed")
        error = VendorMessageErrorResponse(status="error", message=_ERROR_MESSAGE)
        return JSONResponse(status_code=500, content=error.model_dump())


@app.post("/manny_oil_delivery_request")
async def manny_oil_delivery_request(request: MannyOilDeliveryRequestRequest):
    """Accept a Manny's Oil delivery request from the agent."""
    _ensure_call_timestamp(request)
    try:
        return handle_manny_oil_delivery_request(request)
    except Exception:
        logger.exception("manny_oil_delivery_request handler failed")
        error = VendorMessageErrorResponse(status="error", message=_ERROR_MESSAGE)
        return JSONResponse(status_code=500, content=error.model_dump())


@app.post("/manny_oil_general_inquiries")
async def manny_oil_general_inquiries(request: MannyOilGeneralInquiriesRequest):
    """Accept a Manny's Oil general inquiry / callback request from the agent."""
    _ensure_call_timestamp(request)
    try:
        return handle_manny_oil_general_inquiries(request)
    except Exception:
        logger.exception("manny_oil_general_inquiries handler failed")
        error = VendorMessageErrorResponse(status="error", message=_ERROR_MESSAGE)
        return JSONResponse(status_code=500, content=error.model_dump())


@app.post("/elevenlabs_post_call")
async def elevenlabs_post_call(request: Request):
    """Receive ElevenLabs post-call webhook events and forward to Booker.

    Always returns HTTP 200 so ElevenLabs never sees a failure and
    retries — downstream errors are logged, not propagated.
    """
    try:
        body = await request.json()
    except Exception:
        logger.exception("elevenlabs_post_call: could not parse request body")
        return {"accepted": False, "reason": "invalid_json"}

    try:
        return await handle_webhook(body)
    except Exception:
        logger.exception("elevenlabs_post_call: unexpected handler error")
        return {"accepted": True, "forwarded": False, "error": "internal_error"}
