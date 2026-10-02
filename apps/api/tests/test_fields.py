import pytest

from cornerpin.core.fields import normalize_phone


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("208-555-0142", "+12085550142"),
        ("(208) 555 0142", "+12085550142"),
        ("1 208 555 0142", "+12085550142"),
        ("+1 208.555.0142", "+12085550142"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_phone_numbers_are_stored_as_e164(typed: str, stored: str) -> None:
    assert normalize_phone(typed) == stored


@pytest.mark.parametrize(
    "typed", ["555-0142", "44 20 7946 0958", "", "+0 208 555 0142", "call me", "+1234567890123456"]
)
def test_phone_numbers_that_cannot_be_dialled_are_refused(typed: str) -> None:
    with pytest.raises(ValueError, match="phone number"):
        normalize_phone(typed)
