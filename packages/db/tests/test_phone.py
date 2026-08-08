import pytest
from jkr_db.phone import InvalidPhoneNumberError, is_valid, mask_for_display, normalize_e164


def test_normalizes_indian_national_number_to_e164():
    assert normalize_e164("9876543210") == "+919876543210"


def test_normalizes_number_with_existing_country_code():
    assert normalize_e164("+91 98765 43210") == "+919876543210"


def test_rejects_too_short_number():
    with pytest.raises(InvalidPhoneNumberError):
        normalize_e164("12345")


def test_rejects_garbage_input():
    with pytest.raises(InvalidPhoneNumberError):
        normalize_e164("not-a-phone-number")


def test_is_valid_true_and_false():
    assert is_valid("9876543210") is True
    assert is_valid("123") is False


def test_mask_for_display_keeps_prefix_and_last4():
    assert mask_for_display("+919876543210") == "+91••••••3210"


def test_mask_for_display_short_input_returned_unchanged():
    assert mask_for_display("+911") == "+911"
