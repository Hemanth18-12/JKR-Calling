"""E.164 phone number validation/normalization — shared by contacts import,
the campaign safety gate, and suppression lookups so all three agree on what
counts as "the same number." India-biased default region, per spec's India-first
positioning, but works for any region a number is unambiguous for."""

from __future__ import annotations

import phonenumbers


class InvalidPhoneNumberError(ValueError):
    pass


def normalize_e164(raw: str, default_region: str = "IN") -> str:
    """Parse `raw` and return its E.164 form, e.g. '+919876543210'.

    Raises InvalidPhoneNumberError if the number cannot be parsed or is not a
    valid, plausible number for its region.
    """
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumberError(f"Could not parse phone number {raw!r}: {exc}") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumberError(f"{raw!r} is not a valid phone number")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def mask_for_display(e164: str) -> str:
    """'+919876543210' -> '+91••••••3210' — used everywhere a phone number is
    rendered outside a contacts:view_unmasked-permitted view. See
    docs/SECURITY_AND_COMPLIANCE.md §6."""
    if len(e164) <= 6:
        return e164
    country_and_prefix = e164[:3]
    last4 = e164[-4:]
    masked_len = len(e164) - len(country_and_prefix) - len(last4)
    return f"{country_and_prefix}{'•' * max(masked_len, 0)}{last4}"


def is_valid(raw: str, default_region: str = "IN") -> bool:
    try:
        normalize_e164(raw, default_region)
        return True
    except InvalidPhoneNumberError:
        return False
