"""Handlers for the 7 branded-email endpoints.

5 AllPoints HVAC + 2 Manny's Oil Company. All handlers build the
HTML + text bodies via services.email_templates and send through
Resend using the shared OFFICE_EMAIL_RECIPIENTS list. Exceptions
propagate — the api/ layer shapes 5xx responses with the
caller-friendly fallback copy.

The optional `email` and `callTimestamp` fields are forwarded into
the template. The api/ layer fills in callTimestamp with
datetime.utcnow() ISO 8601 when ElevenLabs did not provide one.
"""

import logging

import resend

import config
from models.schemas import (
    CancelEmailRequest,
    GeneralInquiriesEmailRequest,
    MannyOilDeliveryRequestRequest,
    MannyOilGeneralInquiriesRequest,
    RecentServiceEmailRequest,
    RescheduleEmailRequest,
    SchedulingEmailRequest,
    UrgentCallRequest,
)
from services import email_templates

logger = logging.getLogger(__name__)


def _send_branded_email(
    *,
    subject: str,
    html_body: str,
    text_body: str,
    log_label: str,
) -> None:
    if not config.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not set in environment")
    if not config.OFFICE_EMAIL_RECIPIENTS:
        raise RuntimeError("OFFICE_EMAIL_RECIPIENTS is not set in environment")

    resend.api_key = config.RESEND_API_KEY
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
        "%s sent via Resend: id=%s to=%s",
        log_label,
        response["id"],
        config.OFFICE_EMAIL_RECIPIENTS,
    )


# --- AllPoints HVAC ---


def handle_scheduling_email(request: SchedulingEmailRequest) -> dict:
    subject = f"New Appointment Request - {request.customerName}"
    html_body = email_templates.scheduling_email_html(
        customer_name=request.customerName,
        phone=request.phone,
        address=request.address,
        service_issue=request.serviceIssue,
        preferred_times=request.preferredTimes,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    text_body = email_templates.scheduling_email_text(
        customer_name=request.customerName,
        phone=request.phone,
        address=request.address,
        service_issue=request.serviceIssue,
        preferred_times=request.preferredTimes,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="scheduling_email",
    )
    return {
        "status": "ok",
        "message": "Appointment request received. The office will follow up to confirm.",
    }


def handle_reschedule_email(request: RescheduleEmailRequest) -> dict:
    subject = f"Appointment Reschedule Request - {request.customerName}"
    html_body = email_templates.reschedule_email_html(
        customer_name=request.customerName,
        phone=request.phone,
        original_appointment=request.originalAppointment,
        preferred_times=request.preferredTimes,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    text_body = email_templates.reschedule_email_text(
        customer_name=request.customerName,
        phone=request.phone,
        original_appointment=request.originalAppointment,
        preferred_times=request.preferredTimes,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="reschedule_email",
    )
    return {
        "status": "ok",
        "message": "Reschedule request received. The office will follow up to confirm.",
    }


def handle_cancel_email(request: CancelEmailRequest) -> dict:
    subject = f"Appointment Cancellation Request - {request.customerName}"
    html_body = email_templates.cancel_email_html(
        customer_name=request.customerName,
        phone=request.phone,
        appointment_to_cancel=request.appointmentToCancel,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    text_body = email_templates.cancel_email_text(
        customer_name=request.customerName,
        phone=request.phone,
        appointment_to_cancel=request.appointmentToCancel,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="cancel_email",
    )
    return {
        "status": "ok",
        "message": "Cancellation request received. The office will follow up to confirm.",
    }


def handle_general_inquiries_email(request: GeneralInquiriesEmailRequest) -> dict:
    subject = f"Callback Request - {request.customerName}"
    html_body = email_templates.general_inquiries_email_html(
        customer_name=request.customerName,
        phone=request.phone,
        inquiry=request.inquiry,
        preferred_times=request.preferredTimes,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    text_body = email_templates.general_inquiries_email_text(
        customer_name=request.customerName,
        phone=request.phone,
        inquiry=request.inquiry,
        preferred_times=request.preferredTimes,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="general_inquiries_email",
    )
    return {
        "status": "ok",
        "message": "Callback request received. The office will follow up.",
    }


def handle_recent_service_email(request: RecentServiceEmailRequest) -> dict:
    subject = f"Recent Service Follow-up - {request.customerName}"
    html_body = email_templates.recent_service_email_html(
        customer_name=request.customerName,
        phone=request.phone,
        inquiry=request.inquiry,
        preferred_times=request.preferredTimes,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    text_body = email_templates.recent_service_email_text(
        customer_name=request.customerName,
        phone=request.phone,
        inquiry=request.inquiry,
        preferred_times=request.preferredTimes,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="recent_service_email",
    )
    return {
        "status": "ok",
        "message": "Follow-up request received. The office will follow up.",
    }


# --- Manny's Oil Company ---


def handle_manny_oil_delivery_request(request: MannyOilDeliveryRequestRequest) -> dict:
    subject = f"Delivery Request, Manny's Oil - {request.customerName}"
    html_body = email_templates.manny_oil_delivery_request_html(
        customer_name=request.customerName,
        phone=request.phone,
        address=request.address,
        preferred_times=request.preferredTimes,
        client_business_name=config.MANNY_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    text_body = email_templates.manny_oil_delivery_request_text(
        customer_name=request.customerName,
        phone=request.phone,
        address=request.address,
        preferred_times=request.preferredTimes,
        client_business_name=config.MANNY_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="manny_oil_delivery_request",
    )
    return {
        "status": "ok",
        "message": "Delivery request received. The office will follow up to confirm.",
    }


def handle_manny_oil_general_inquiries(request: MannyOilGeneralInquiriesRequest) -> dict:
    subject = f"Callback Request, Manny's Oil - {request.customerName}"
    html_body = email_templates.manny_oil_general_inquiries_html(
        customer_name=request.customerName,
        phone=request.phone,
        inquiry=request.inquiry,
        preferred_times=request.preferredTimes,
        client_business_name=config.MANNY_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    text_body = email_templates.manny_oil_general_inquiries_text(
        customer_name=request.customerName,
        phone=request.phone,
        inquiry=request.inquiry,
        preferred_times=request.preferredTimes,
        client_business_name=config.MANNY_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="manny_oil_general_inquiries",
    )
    return {
        "status": "ok",
        "message": "Callback request received. The office will follow up.",
    }


# --- Urgent call: 3 phases of email ---


def handle_urgent_initial_email(request: UrgentCallRequest) -> None:
    """Fires from /urgent_call entry before the Twilio retry loop starts."""
    subject = f"URGENT SERVICE REQUEST - {request.customerName}"
    html_body = email_templates.urgent_initial_email_html(
        customer_name=request.customerName,
        phone=request.phone,
        address=request.address,
        service_issue=request.serviceIssue,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    text_body = email_templates.urgent_initial_email_text(
        customer_name=request.customerName,
        phone=request.phone,
        address=request.address,
        service_issue=request.serviceIssue,
        client_business_name=config.CLIENT_BUSINESS_NAME,
        email=request.email,
        call_timestamp=request.callTimestamp,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="urgent_initial_email",
    )


def handle_urgent_confirmation_email(row: dict, confirmed_at: str) -> None:
    """Fires when the recipient pressed a digit on the Twilio call.

    `row` is the Supabase urgent_call_attempts row (snake_case
    column names).
    """
    customer_name = row["customer_name"]
    subject = f"Urgent Call Confirmed - {customer_name}"
    html_body = email_templates.urgent_confirmation_email_html(
        customer_name=customer_name,
        phone=row["customer_phone"],
        address=row["customer_address"],
        service_issue=row["service_issue"],
        confirmed_at=confirmed_at,
        client_business_name=config.CLIENT_BUSINESS_NAME,
    )
    text_body = email_templates.urgent_confirmation_email_text(
        customer_name=customer_name,
        phone=row["customer_phone"],
        address=row["customer_address"],
        service_issue=row["service_issue"],
        confirmed_at=confirmed_at,
        client_business_name=config.CLIENT_BUSINESS_NAME,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="urgent_confirmation_email",
    )


def handle_urgent_never_confirmed_email(row: dict, attempts_made: int) -> None:
    """Fires when all 3 phone attempts failed without a digit press."""
    customer_name = row["customer_name"]
    subject = f"URGENT - All Phone Attempts Failed - {customer_name}"
    html_body = email_templates.urgent_never_confirmed_email_html(
        customer_name=customer_name,
        phone=row["customer_phone"],
        address=row["customer_address"],
        service_issue=row["service_issue"],
        attempts_made=attempts_made,
        client_business_name=config.CLIENT_BUSINESS_NAME,
    )
    text_body = email_templates.urgent_never_confirmed_email_text(
        customer_name=customer_name,
        phone=row["customer_phone"],
        address=row["customer_address"],
        service_issue=row["service_issue"],
        attempts_made=attempts_made,
        client_business_name=config.CLIENT_BUSINESS_NAME,
    )
    _send_branded_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        log_label="urgent_never_confirmed_email",
    )
