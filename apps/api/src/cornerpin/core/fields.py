"""Field types shared by request bodies: email addresses, phone numbers and time zones."""

import re
from functools import cache
from typing import Annotated
from zoneinfo import available_timezones

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, Field

from cornerpin.core.config import get_settings

# Must match the CHECK constraint on users.phone, inquiries.phone and hold_requests.phone.
E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")
SEPARATORS = re.compile(r"[\s().-]")


def _email_address(value: str) -> str:
    """Normalized address. Locally .test domains are allowed, so Mailpit can receive them."""
    try:
        return validate_email(
            value, check_deliverability=False, test_environment=get_settings().is_local
        ).normalized
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc


def normalize_phone(value: str) -> str:
    """E.164 from what people type. Without a leading + the number must be a US one (ten
    digits, or eleven starting with 1), since buyers are mostly in Idaho; a seven-digit local
    number is refused rather than read as some other country's."""
    digits = SEPARATORS.sub("", value)
    if digits.startswith("+"):
        candidate = digits
    elif len(digits) == 10:
        candidate = f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        candidate = f"+{digits}"
    else:
        candidate = ""
    if not E164.fullmatch(candidate):
        raise ValueError("Enter a phone number like 208-555-0142, or +44 20 7946 0958")
    return candidate


@cache
def _time_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def _time_zone(value: str) -> str:
    if value not in _time_zones():
        raise ValueError("Not a known time zone, e.g. America/Boise")
    return value


EmailAddress = Annotated[
    str, AfterValidator(_email_address), Field(json_schema_extra={"format": "email"})
]
Phone = Annotated[str, AfterValidator(normalize_phone), Field(max_length=32)]
TimeZone = Annotated[str, AfterValidator(_time_zone)]
