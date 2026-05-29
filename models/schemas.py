"""Pydantic request and response models.

One model per endpoint, named for the endpoint. Schemas are the
contract between the agent's webhook tool config and the backend.

Phone fields use the shared PhoneField alias so every endpoint
normalizes incoming numbers to digits-only with the same length
guard. JSON field names use camelCase to match the agent's webhook
tool config (customerName, preferredTimes, etc.).

Two optional fields appear on every email endpoint:
- `email` — optional caller email; renders in the template only
  when present. ElevenLabs flows do not always collect it.
- `callTimestamp` — optional ISO 8601 string from ElevenLabs's
  `{{system__time_utc}}`. If absent, the api/ layer fills in
  datetime.utcnow() at request boundary.
"""

from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, AliasChoices, BaseModel, ConfigDict, Field

from services.utils import normalize_phone


def _validate_phone(raw: str) -> str:
    normalized = normalize_phone(raw)
    if len(normalized) < 7:
        raise ValueError("phone must contain at least 7 digits")
    return normalized


PhoneField = Annotated[str, AfterValidator(_validate_phone)]


class _OptionalEmailMixin(BaseModel):
    """Shared optional fields present on every email endpoint."""

    email: Optional[str] = None
    callTimestamp: Optional[str] = None


# --- AllPoints HVAC endpoints ---


class SchedulingEmailRequest(_OptionalEmailMixin):
    """Request body for POST /scheduling_email."""

    customerName: str = Field(min_length=1)
    phone: PhoneField
    address: str = Field(min_length=1)
    serviceIssue: str = Field(min_length=1)
    preferredTimes: str = Field(min_length=1)


class RescheduleEmailRequest(_OptionalEmailMixin):
    """Request body for POST /reschedule_email."""

    customerName: str = Field(min_length=1)
    phone: PhoneField
    originalAppointment: str = Field(min_length=1)
    preferredTimes: str = Field(min_length=1)


class CancelEmailRequest(_OptionalEmailMixin):
    """Request body for POST /cancel_email."""

    customerName: str = Field(min_length=1)
    phone: PhoneField
    appointmentToCancel: str = Field(min_length=1)


class GeneralInquiriesEmailRequest(_OptionalEmailMixin):
    """Request body for POST /general_inquiries_email."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    customerName: str = Field(min_length=1)
    phone: PhoneField
    inquiry: str = Field(
        min_length=1,
        validation_alias=AliasChoices("inquiry", "Inquiry"),
    )
    preferredTimes: str = Field(min_length=1)


class RecentServiceEmailRequest(_OptionalEmailMixin):
    """Request body for POST /recent_service_email."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    customerName: str = Field(min_length=1)
    phone: PhoneField
    inquiry: str = Field(
        min_length=1,
        validation_alias=AliasChoices("inquiry", "Inquiry"),
    )
    preferredTimes: str = Field(min_length=1)


# --- Manny's Oil Company endpoints ---


class MannyOilDeliveryRequestRequest(_OptionalEmailMixin):
    """Request body for POST /manny_oil_delivery_request."""

    customerName: str = Field(min_length=1)
    phone: PhoneField
    address: str = Field(min_length=1)
    preferredTimes: str = Field(min_length=1)


class MannyOilGeneralInquiriesRequest(_OptionalEmailMixin):
    """Request body for POST /manny_oil_general_inquiries."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    customerName: str = Field(min_length=1)
    phone: PhoneField
    inquiry: str = Field(
        min_length=1,
        validation_alias=AliasChoices("inquiry", "Inquiry"),
    )
    preferredTimes: str = Field(min_length=1)


# --- Vendor message (mirror T&T exactly; no optional fields) ---


class VendorMessageRequest(BaseModel):
    """Request body for POST /vendor_message."""

    name: str = Field(min_length=1)
    company: str = Field(min_length=1)
    phone: PhoneField
    reason: str = Field(min_length=1)


# --- Urgent call (Twilio + Supabase + asyncio retry loop) ---


class UrgentCallRequest(_OptionalEmailMixin):
    """Request body for POST /urgent_call.

    Required fields mirror the existing AllPoints_urgent_call
    Make.com tool schema. Optional fields (email, callTimestamp)
    follow the convention of the other AllPoints email endpoints.
    """

    customerName: str = Field(min_length=1)
    phone: PhoneField
    address: str = Field(min_length=1)
    serviceIssue: str = Field(min_length=1)


# --- Response models ---


class VendorMessageResponse(BaseModel):
    """Success response for POST /vendor_message."""

    status: Literal["ok"]
    message: str


class VendorMessageErrorResponse(BaseModel):
    """Server-error (5xx) response shape.

    The agent speaks the `message` field back to the caller. Reused
    for all email endpoints — same shape, same failure copy.
    """

    status: Literal["error"]
    message: str


class EmailResponse(BaseModel):
    """Success response for the branded-email endpoints."""

    status: Literal["ok"]
    message: str


class UrgentCallResponse(BaseModel):
    """Success response for POST /urgent_call.

    `attempt_id` is the UUID of the row created in
    Supabase.urgent_call_attempts — useful for tracing logs and for
    the agent to acknowledge in its spoken response.
    """

    status: Literal["ok"]
    message: str
    attempt_id: str
