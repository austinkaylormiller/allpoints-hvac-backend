"""HTML and plain-text email templates for outbound notifications.

Templates follow the Booker AI brand spec: clean Inter typography
(with system fallback), a colored left border on the header card,
no logo image, no emoji decoration in headers, and a footer
wordmark + receipt-context line.

Two businesses share this backend — AllPoints HVAC and Manny's Oil
Company. The footer/tagline business name is driven by the
`client_business_name` argument the caller passes in. The 5
AllPoints endpoints pass AllPoints HVAC; the 2 Manny's Oil
endpoints pass Manny's Oil Company.

Optional fields (email, call_timestamp) render only when present —
callers pass `None` to omit them.
"""

import html
from datetime import datetime
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

# TODO: All current clients (AllPoints HVAC, T&T HVAC, Branded
# Barber) operate in Eastern time. When the first non-Eastern
# client onboards, move this to a per-client config var
# (CLIENT_DISPLAY_TZ or similar) and thread it through the
# template builders.
_DISPLAY_TZ = ZoneInfo("America/New_York")


def _format_confirmed_at(iso_string: str) -> str:
    """Render a UTC ISO 8601 timestamp as Eastern Time.

    Example: '2026-05-27T21:16:00+00:00' -> 'May 27, 2026 at 5:16 PM ET'

    Returns the input unchanged on parse failure — better to show
    the raw value than to ship an email with a blank Confirmed At.
    The %-d / %-I formatters are POSIX strftime extensions
    (macOS + Linux); Railway runs Linux so this is safe.
    """
    if not iso_string:
        return iso_string
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        local = dt.astimezone(_DISPLAY_TZ)
        return local.strftime("%B %-d, %Y at %-I:%M %p ET")
    except (ValueError, TypeError):
        return iso_string

_FONT = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

# Accent palette. All values share warm/cool Booker tones — they read
# distinctly from each other while remaining legible in light and dark
# email clients.
ACCENT_ORANGE_CLAY = "#c66140"
ACCENT_AMBER_GOLD = "#b8842a"
ACCENT_EARTHY_RED = "#9c4a3f"
ACCENT_BLUE_GRAY = "#5a7f8b"


def _format_phone(phone: str) -> str:
    """Format a 10-digit phone as 555-123-4567; otherwise return as-is."""
    if len(phone) == 10 and phone.isdigit():
        return f"{phone[:3]}-{phone[3:6]}-{phone[6:]}"
    return phone


# ---- Section descriptors ----
# Each section is a dict in one of three shapes:
#   {"type": "rows",      "heading": str, "rows": [(label, value), ...]}
#   {"type": "paragraph", "heading": str, "text": str}
#   {"type": "highlight", "heading": str, "text": str}


def _rows_html(rows: Iterable[tuple[str, str]]) -> str:
    row_style = (
        f"font-family:{_FONT}; font-size:15px; line-height:1.6; "
        "color:#141413; margin:0;"
    )
    rows_list = list(rows)
    pieces = []
    for i, (label, value) in enumerate(rows_list):
        last = i == len(rows_list) - 1
        spacing = "" if last else " padding-bottom:8px;"
        pieces.append(
            f'<div style="{row_style}{spacing}">'
            f'<strong style="font-weight:600;">{html.escape(label)}:</strong> '
            f'<span style="font-weight:400;">{html.escape(value)}</span>'
            f"</div>"
        )
    return "".join(pieces)


def _heading_html(heading: str) -> str:
    return (
        f'<div style="font-family:{_FONT}; font-weight:600; font-size:16px; '
        f'color:#141413; margin-top:28px; margin-bottom:12px;">'
        f"{html.escape(heading)}:</div>"
    )


def _paragraph_html(text: str) -> str:
    return (
        f'<div style="font-family:{_FONT}; font-size:15px; line-height:1.6; '
        f'color:#141413; padding-left:16px;">'
        f"{html.escape(text)}"
        f"</div>"
    )


def _highlight_html(text: str) -> str:
    return (
        f'<div style="font-family:{_FONT}; font-size:15px; line-height:1.6; '
        f'color:#141413; background-color:#f9f8f5; '
        f'padding:12px 16px; border-radius:4px;">'
        f"{html.escape(text)}"
        f"</div>"
    )


def _section_html(section: dict) -> str:
    body_html = _heading_html(section["heading"])
    kind = section["type"]
    if kind == "rows":
        body_html += f'<div style="padding-left:16px;">{_rows_html(section["rows"])}</div>'
    elif kind == "paragraph":
        body_html += _paragraph_html(section["text"])
    elif kind == "highlight":
        body_html += _highlight_html(section["text"])
    else:
        raise ValueError(f"unknown section type: {kind!r}")
    return body_html


def render_email_html(
    *,
    header: str,
    tagline: str,
    accent_hex: str,
    sections: list[dict],
    client_business_name: str,
    call_timestamp: Optional[str] = None,
) -> str:
    """Render the full HTML body for a notification email.

    `call_timestamp` is accepted to keep the parameter contract
    stable for callers, but is intentionally not rendered — the
    received-at line clutters the footer and the agent/log
    already records the time.
    """
    e_header = html.escape(header)
    e_tagline = html.escape(tagline)
    e_client = html.escape(client_business_name)
    sections_html = "".join(_section_html(s) for s in sections)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e_header}</title>
</head>
<body style="margin:0; padding:0; background-color:#f4f4f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f4f4f2;">
<tr>
<td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px; width:100%; background-color:#ffffff;">
<tr>
<td style="padding:32px;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td style="border-left:3px solid {accent_hex}; padding:12px 20px;">
<div style="font-family:{_FONT}; font-weight:600; font-size:20px; color:#141413;">{e_header}</div>
<div style="font-family:{_FONT}; font-weight:400; font-size:15px; color:#141413; margin-top:4px;">{e_tagline}</div>
</td>
</tr>
</table>

{sections_html}

<div style="margin-top:40px; padding-top:20px; border-top:1px solid #e5e5e5;">
<div style="font-family:{_FONT}; font-weight:400; font-size:13px; line-height:1.5; color:#6c6b67;">Booker AI · <a href="https://getbookerai.com" style="color: #6c6b67; text-decoration: underline;">getbookerai.com</a></div>
<div style="font-family:{_FONT}; font-weight:400; font-size:13px; line-height:1.5; color:#6c6b67;">You're receiving this because Booker answered a call for {e_client}.</div>
</div>

</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>
"""


def _section_text(section: dict) -> str:
    heading = f"{section['heading']}:"
    kind = section["type"]
    if kind == "rows":
        body = "\n".join(f"{label}: {value}" for label, value in section["rows"])
    elif kind in ("paragraph", "highlight"):
        body = section["text"]
    else:
        raise ValueError(f"unknown section type: {kind!r}")
    return f"{heading}\n{body}"


def render_email_text(
    *,
    header: str,
    tagline: str,
    sections: list[dict],
    client_business_name: str,
    call_timestamp: Optional[str] = None,
) -> str:
    """Render the plain-text fallback body for a notification email.

    `call_timestamp` is accepted to keep the parameter contract
    stable for callers, but is intentionally not rendered.
    """
    sections_text = "\n\n".join(_section_text(s) for s in sections)
    return (
        f"{header}\n"
        f"\n"
        f"{tagline}\n"
        f"\n"
        f"{sections_text}\n"
        f"\n"
        f"Booker AI · getbookerai.com\n"
        f"You're receiving this because Booker answered a call for {client_business_name}.\n"
    )


def _customer_rows(
    customer_name: str,
    phone: str,
    email: Optional[str] = None,
    address: Optional[str] = None,
) -> list[tuple[str, str]]:
    """Build the standard customer-information rows.

    Email is included only when truthy; address only when supplied.
    """
    rows: list[tuple[str, str]] = [
        ("Name", customer_name),
        ("Phone", _format_phone(phone)),
    ]
    if email:
        rows.append(("Email", email))
    if address:
        rows.append(("Address", address))
    return rows


# ---- Per-endpoint convenience builders ----


# vendor_message (mirror T&T verbatim — no email/timestamp fields)

def _vendor_message_sections(name: str, company: str, phone: str, reason: str) -> list[dict]:
    return [
        {
            "type": "rows",
            "heading": "Vendor information",
            "rows": [
                ("Name", name),
                ("Company", company),
                ("Phone", _format_phone(phone)),
                ("Reason", reason),
            ],
        },
    ]


def vendor_message_html(
    name: str,
    company: str,
    phone: str,
    reason: str,
    client_business_name: str,
) -> str:
    return render_email_html(
        header="Vendor Message",
        tagline=f"A vendor has left a message for {client_business_name}.",
        accent_hex=ACCENT_ORANGE_CLAY,
        sections=_vendor_message_sections(name, company, phone, reason),
        client_business_name=client_business_name,
    )


def vendor_message_text(
    name: str,
    company: str,
    phone: str,
    reason: str,
    client_business_name: str,
) -> str:
    return render_email_text(
        header="Vendor Message",
        tagline=f"A vendor has left a message for {client_business_name}.",
        sections=_vendor_message_sections(name, company, phone, reason),
        client_business_name=client_business_name,
    )


# AllPoints HVAC: scheduling

def _scheduling_sections(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    preferred_times: str,
    email: Optional[str] = None,
) -> list[dict]:
    return [
        {
            "type": "rows",
            "heading": "Customer Information",
            "rows": _customer_rows(customer_name, phone, email=email, address=address),
        },
        {"type": "paragraph", "heading": "Service Request", "text": service_issue},
        {"type": "highlight", "heading": "Preferred Times", "text": preferred_times},
    ]


def scheduling_email_html(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="New Appointment Request",
        tagline=f"A customer has requested to schedule a service appointment with {client_business_name}.",
        accent_hex=ACCENT_ORANGE_CLAY,
        sections=_scheduling_sections(
            customer_name, phone, address, service_issue, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def scheduling_email_text(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="New Appointment Request",
        tagline=f"A customer has requested to schedule a service appointment with {client_business_name}.",
        sections=_scheduling_sections(
            customer_name, phone, address, service_issue, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


# AllPoints HVAC: reschedule

def _reschedule_sections(
    customer_name: str,
    phone: str,
    original_appointment: str,
    preferred_times: str,
    email: Optional[str] = None,
) -> list[dict]:
    return [
        {
            "type": "rows",
            "heading": "Customer Information",
            "rows": _customer_rows(customer_name, phone, email=email),
        },
        {"type": "highlight", "heading": "Original Appointment", "text": original_appointment},
        {"type": "highlight", "heading": "New Preferred Times", "text": preferred_times},
    ]


def reschedule_email_html(
    customer_name: str,
    phone: str,
    original_appointment: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="Appointment Reschedule Request",
        tagline=f"A customer has requested to reschedule their {client_business_name} appointment.",
        accent_hex=ACCENT_AMBER_GOLD,
        sections=_reschedule_sections(
            customer_name, phone, original_appointment, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def reschedule_email_text(
    customer_name: str,
    phone: str,
    original_appointment: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="Appointment Reschedule Request",
        tagline=f"A customer has requested to reschedule their {client_business_name} appointment.",
        sections=_reschedule_sections(
            customer_name, phone, original_appointment, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


# AllPoints HVAC: cancel

def _cancel_sections(
    customer_name: str,
    phone: str,
    appointment_to_cancel: str,
    email: Optional[str] = None,
) -> list[dict]:
    return [
        {
            "type": "rows",
            "heading": "Customer Information",
            "rows": _customer_rows(customer_name, phone, email=email),
        },
        {"type": "highlight", "heading": "Appointment to Cancel", "text": appointment_to_cancel},
    ]


def cancel_email_html(
    customer_name: str,
    phone: str,
    appointment_to_cancel: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="Appointment Cancellation Request",
        tagline=f"A customer has requested to cancel their {client_business_name} appointment.",
        accent_hex=ACCENT_EARTHY_RED,
        sections=_cancel_sections(customer_name, phone, appointment_to_cancel, email=email),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def cancel_email_text(
    customer_name: str,
    phone: str,
    appointment_to_cancel: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="Appointment Cancellation Request",
        tagline=f"A customer has requested to cancel their {client_business_name} appointment.",
        sections=_cancel_sections(customer_name, phone, appointment_to_cancel, email=email),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


# AllPoints HVAC: general inquiries

def _general_inquiries_sections(
    customer_name: str,
    phone: str,
    inquiry: str,
    preferred_times: str,
    email: Optional[str] = None,
) -> list[dict]:
    return [
        {
            "type": "rows",
            "heading": "Customer Information",
            "rows": _customer_rows(customer_name, phone, email=email),
        },
        {"type": "paragraph", "heading": "Callback Request", "text": inquiry},
        {
            "type": "highlight",
            "heading": "Preferred Callback Times",
            "text": preferred_times,
        },
    ]


def general_inquiries_email_html(
    customer_name: str,
    phone: str,
    inquiry: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="Callback Requested",
        tagline=f"A customer has requested a callback from {client_business_name}.",
        accent_hex=ACCENT_BLUE_GRAY,
        sections=_general_inquiries_sections(
            customer_name, phone, inquiry, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def general_inquiries_email_text(
    customer_name: str,
    phone: str,
    inquiry: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="Callback Requested",
        tagline=f"A customer has requested a callback from {client_business_name}.",
        sections=_general_inquiries_sections(
            customer_name, phone, inquiry, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


# AllPoints HVAC: recent service follow-up

def _recent_service_sections(
    customer_name: str,
    phone: str,
    inquiry: str,
    preferred_times: str,
    email: Optional[str] = None,
) -> list[dict]:
    return [
        {
            "type": "rows",
            "heading": "Customer Information",
            "rows": _customer_rows(customer_name, phone, email=email),
        },
        {"type": "paragraph", "heading": "Follow-up Request", "text": inquiry},
        {
            "type": "highlight",
            "heading": "Preferred Callback Times",
            "text": preferred_times,
        },
    ]


def recent_service_email_html(
    customer_name: str,
    phone: str,
    inquiry: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="Recent Service Follow-up",
        tagline=f"A customer has requested a callback after a recent {client_business_name} service visit.",
        accent_hex=ACCENT_BLUE_GRAY,
        sections=_recent_service_sections(
            customer_name, phone, inquiry, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def recent_service_email_text(
    customer_name: str,
    phone: str,
    inquiry: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="Recent Service Follow-up",
        tagline=f"A customer has requested a callback after a recent {client_business_name} service visit.",
        sections=_recent_service_sections(
            customer_name, phone, inquiry, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


# Manny's Oil Company: delivery request

def _manny_oil_delivery_sections(
    customer_name: str,
    phone: str,
    address: str,
    preferred_times: str,
    email: Optional[str] = None,
) -> list[dict]:
    return [
        {
            "type": "rows",
            "heading": "Customer Information",
            "rows": _customer_rows(customer_name, phone, email=email, address=address),
        },
        {
            "type": "highlight",
            "heading": "Preferred Delivery Times",
            "text": preferred_times,
        },
    ]


def manny_oil_delivery_request_html(
    customer_name: str,
    phone: str,
    address: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="Oil Delivery Request",
        tagline=f"A customer has requested an oil delivery from {client_business_name}.",
        accent_hex=ACCENT_ORANGE_CLAY,
        sections=_manny_oil_delivery_sections(
            customer_name, phone, address, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def manny_oil_delivery_request_text(
    customer_name: str,
    phone: str,
    address: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="Oil Delivery Request",
        tagline=f"A customer has requested an oil delivery from {client_business_name}.",
        sections=_manny_oil_delivery_sections(
            customer_name, phone, address, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


# Manny's Oil Company: general inquiries

def _manny_oil_general_sections(
    customer_name: str,
    phone: str,
    inquiry: str,
    preferred_times: str,
    email: Optional[str] = None,
) -> list[dict]:
    return [
        {
            "type": "rows",
            "heading": "Customer Information",
            "rows": _customer_rows(customer_name, phone, email=email),
        },
        {"type": "paragraph", "heading": "Callback Request", "text": inquiry},
        {
            "type": "highlight",
            "heading": "Preferred Callback Times",
            "text": preferred_times,
        },
    ]


def manny_oil_general_inquiries_html(
    customer_name: str,
    phone: str,
    inquiry: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="Callback Requested",
        tagline=f"A customer has requested a callback from {client_business_name}.",
        accent_hex=ACCENT_BLUE_GRAY,
        sections=_manny_oil_general_sections(
            customer_name, phone, inquiry, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def manny_oil_general_inquiries_text(
    customer_name: str,
    phone: str,
    inquiry: str,
    preferred_times: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="Callback Requested",
        tagline=f"A customer has requested a callback from {client_business_name}.",
        sections=_manny_oil_general_sections(
            customer_name, phone, inquiry, preferred_times, email=email
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


# Urgent dispatch — initial, confirmed, never-confirmed. All three
# share the earthy-red accent (stop/alert in the warm family); the
# subject and tagline carry the variant.

def _urgent_sections(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    email: Optional[str] = None,
    extra_highlight: Optional[tuple[str, str]] = None,
) -> list[dict]:
    sections: list[dict] = [
        {
            "type": "rows",
            "heading": "Customer Information",
            "rows": _customer_rows(customer_name, phone, email=email, address=address),
        },
        {"type": "paragraph", "heading": "Urgent Service Request", "text": service_issue},
    ]
    if extra_highlight is not None:
        heading, text = extra_highlight
        sections.append({"type": "highlight", "heading": heading, "text": text})
    return sections


def urgent_initial_email_html(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="URGENT — Service Request",
        tagline=(
            "An urgent service request has been received and requires "
            "immediate attention. The owner is being contacted by phone now."
        ),
        accent_hex=ACCENT_EARTHY_RED,
        sections=_urgent_sections(customer_name, phone, address, service_issue, email=email),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def urgent_initial_email_text(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="URGENT — Service Request",
        tagline=(
            "An urgent service request has been received and requires "
            "immediate attention. The owner is being contacted by phone now."
        ),
        sections=_urgent_sections(customer_name, phone, address, service_issue, email=email),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def urgent_confirmation_email_html(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    confirmed_at: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="Urgent Call Confirmed",
        tagline="The owner has confirmed receipt of the urgent dispatch.",
        accent_hex=ACCENT_EARTHY_RED,
        sections=_urgent_sections(
            customer_name,
            phone,
            address,
            service_issue,
            email=email,
            extra_highlight=("Confirmed At", _format_confirmed_at(confirmed_at)),
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def urgent_confirmation_email_text(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    confirmed_at: str,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="Urgent Call Confirmed",
        tagline="The owner has confirmed receipt of the urgent dispatch.",
        sections=_urgent_sections(
            customer_name,
            phone,
            address,
            service_issue,
            email=email,
            extra_highlight=("Confirmed At", _format_confirmed_at(confirmed_at)),
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def urgent_never_confirmed_email_html(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    attempts_made: int,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_html(
        header="URGENT — All Phone Attempts Failed",
        tagline=(
            f"Unable to reach the owner by phone after {attempts_made} attempts. "
            "Manual follow-up required immediately."
        ),
        accent_hex=ACCENT_EARTHY_RED,
        sections=_urgent_sections(
            customer_name,
            phone,
            address,
            service_issue,
            email=email,
            extra_highlight=(
                "Action Required",
                "Phone outreach to the owner has not succeeded. "
                "Reach the customer directly using the contact details above.",
            ),
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )


def urgent_never_confirmed_email_text(
    customer_name: str,
    phone: str,
    address: str,
    service_issue: str,
    attempts_made: int,
    client_business_name: str,
    email: Optional[str] = None,
    call_timestamp: Optional[str] = None,
) -> str:
    return render_email_text(
        header="URGENT — All Phone Attempts Failed",
        tagline=(
            f"Unable to reach the owner by phone after {attempts_made} attempts. "
            "Manual follow-up required immediately."
        ),
        sections=_urgent_sections(
            customer_name,
            phone,
            address,
            service_issue,
            email=email,
            extra_highlight=(
                "Action Required",
                "Phone outreach to the owner has not succeeded. "
                "Reach the customer directly using the contact details above.",
            ),
        ),
        client_business_name=client_business_name,
        call_timestamp=call_timestamp,
    )
