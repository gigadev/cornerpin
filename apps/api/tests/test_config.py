"""Outside local, the API refuses to start with local defaults or half-configured features, so a
deploy missing a secret fails loudly instead of running insecurely (ADR-032, ADR-040, ADR-048)."""

import base64

import pytest
from pydantic import ValidationError

from cornerpin.core.config import Settings

PRODUCTION: dict[str, object] = {
    "environment": "production",
    "secret_key": "a-production-secret-key-of-reasonable-length",
    "turnstile_site_key": "0x4AAAAAA-site",
    "turnstile_secret_key": "0x4AAAAAA-secret",
    "integrations_key": base64.b64encode(b"p" * 32).decode(),
    "decisioning_url": "https://decisioning-1.us-west1.run.app",
}


def settings(**changes: object) -> Settings:
    return Settings.model_validate({**PRODUCTION, **changes})


def test_a_complete_production_configuration_starts() -> None:
    assert settings().is_local is False


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"integrations_key": Settings().integrations_key}, "INTEGRATIONS_KEY must be set"),
        ({"secret_key": Settings().secret_key}, "SECRET_KEY must be set"),
        ({"inbound_email_domain": "reply.cornerpin.app"}, "RESEND_WEBHOOK_SECRET"),
        ({"email_backend": "resend"}, "RESEND_API_KEY must be set"),
        ({"decisioning_url": None}, "DECISIONING_URL must be set"),
    ],
)
def test_production_refuses_local_defaults_and_half_set_features(
    changes: dict[str, object], problem: str
) -> None:
    with pytest.raises(ValidationError, match=problem):
        settings(**changes)
