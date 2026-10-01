import time

import pytest

from cornerpin.core.auth.tokens import hash_token, new_token, safe_next, sign, unsign


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("/app", "/app"),
        ("/juniper-bench/lots/7?x=1", "/juniper-bench/lots/7?x=1"),
        (None, "/"),
        ("", "/"),
        ("https://evil.example", "/"),
        ("//evil.example", "/"),
        ("/\\evil.example", "/"),
        ("app", "/"),
    ],
)
def test_safe_next(given: str | None, expected: str) -> None:
    assert safe_next(given) == expected


def test_new_token_hash_matches() -> None:
    raw, digest = new_token()
    assert hash_token(raw) == digest
    assert len(raw) >= 40


def test_sign_round_trip() -> None:
    signed = sign({"state": "abc"}, "secret")
    assert unsign(signed, "secret", max_age_seconds=60) == {"state": "abc"}


def test_unsign_rejects_tampering_wrong_secret_and_age(monkeypatch: pytest.MonkeyPatch) -> None:
    signed = sign({"state": "abc"}, "secret")
    body, mac = signed.split(".")
    assert unsign(f"{body}x.{mac}", "secret", max_age_seconds=60) is None
    assert unsign(signed, "other", max_age_seconds=60) is None
    assert unsign("garbage", "secret", max_age_seconds=60) is None

    later = time.time() + 120
    monkeypatch.setattr(time, "time", lambda: later)
    assert unsign(signed, "secret", max_age_seconds=60) is None
