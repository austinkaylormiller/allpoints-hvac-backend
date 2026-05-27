"""Shared utilities for the services layer.

Currently houses normalize_phone() for phone number normalization.
Future helpers (datetime formatting, address parsing) belong here.
"""

import re

_NON_DIGITS = re.compile(r"[^0-9]")

# Spoken-word digits, for the defensive fallback in normalize_phone().
# "oh" is a common spoken form of zero.
_SPOKEN_DIGITS = {
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}

_WORD = re.compile(r"[a-z]+", re.IGNORECASE)


def _convert_spoken_digits(raw: str) -> str:
    """Replace spoken-word digits with their numeral, leaving other text alone."""
    return _WORD.sub(
        lambda m: _SPOKEN_DIGITS.get(m.group(0).lower(), m.group(0)),
        raw,
    )


def normalize_phone(raw: str) -> str:
    """Reduce a phone number to digits only.

    First, any spoken-word digits ("five-five-five") are converted to
    numerals as a defensive fallback for agents that pass the number as
    words rather than digits. Then every character that isn't 0-9 is
    stripped. If the result is exactly 11 digits and starts with "1",
    the leading US country code is dropped and the last 10 digits are
    returned. An empty string is a valid return value when the input
    had no digits — minimum-length enforcement lives in the Pydantic
    validator, not here.

    Examples:
      "555-1234"        -> "5551234"
      "(555) 123-4567"  -> "5551234567"
      "+1 555 123 4567" -> "5551234567"
      "1-800-555-1234"  -> "8005551234"
      "five-five-five, two-one-three, four-seven-eight-nine"
                        -> "5552134789"
      "no number"       -> ""
    """
    digits = _NON_DIGITS.sub("", _convert_spoken_digits(raw))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits
