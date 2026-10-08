from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/src/cornerpin/core/config.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[5]

# Cloudflare's published always-pass Turnstile test keys (CLAUDE.md). Local only.
TURNSTILE_TEST_SITE_KEY = "1x00000000000000000000AA"
TURNSTILE_TEST_SECRET_KEY = "1x0000000000000000000000000000000AA"  # noqa: S105 -- public test key
LOCAL_SECRET_KEY = "local-development-only-not-a-secret"  # noqa: S105 -- refused outside local
# "local-integrations-key-32-bytes!", base64: seals local integration credentials only.
LOCAL_INTEGRATIONS_KEY = "bG9jYWwtaW50ZWdyYXRpb25zLWtleS0zMi1ieXRlcyE="


class Settings(BaseSettings):
    """Configuration from the environment; locally from the repo-root .env file."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "local"
    # Owner role: migrations and seeding only.
    database_url: str = "postgresql+psycopg://cornerpin:cornerpin@localhost:5434/cornerpin"
    # Non-owner login role the API uses (ADR-021). Locally, the migration sets its password from
    # this URL; elsewhere the role's password is provisioned with the infrastructure.
    api_database_url: str = (
        "postgresql+psycopg://cornerpin_api:cornerpin_api@localhost:5434/cornerpin"
    )

    # The origin people use; links in emails and the Origin check on writes use it.
    web_origin: str = "http://localhost:3300"
    # Signs short-lived OAuth state. Must be set outside local.
    secret_key: str = LOCAL_SECRET_KEY

    session_days: int = 30
    magic_link_minutes: int = 15
    magic_links_per_15_minutes: int = 5

    turnstile_site_key: str = TURNSTILE_TEST_SITE_KEY
    turnstile_secret_key: str = TURNSTILE_TEST_SECRET_KEY

    # Google sign-in stays dormant until both are set (ADR-008).
    google_client_id: str | None = None
    google_client_secret: str | None = None

    email_backend: Literal["smtp", "resend"] = "smtp"
    email_from: str = "Cornerpin <no-reply@cornerpin.app>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    resend_api_key: str | None = None
    # Replies to outreach (P2-04, ADR-037): the subdomain whose mail Resend receives, and the
    # signing secret of the Resend webhook that reports it. Without a domain, outreach replies
    # go to the owner's own address. Locally a domain alone lets /v1/dev/inbound-email play
    # the provider.
    inbound_email_domain: str | None = None
    resend_webhook_secret: str | None = None

    # The outreach agent (P2-05, ADR-038) stays dormant until the key is set: no follow-ups are
    # queued and no model is called. It's pay as you go, so the key goes in only after a yes.
    anthropic_api_key: str | None = None
    agent_model: str = "claude-sonnet-5-5"
    # How long after a consented inquiry the first follow-up is written.
    agent_follow_up_minutes: int = 15

    # Per-tenant integrations (ADR-040). Their credentials are sealed with this key (32 bytes,
    # base64) in the database; the local default is refused elsewhere.
    integrations_key: str = LOCAL_INTEGRATIONS_KEY
    # Cornerpin's Slack app (P2-07). Slack stays dormant until all three are set.
    slack_client_id: str | None = None
    slack_client_secret: str | None = None
    slack_signing_secret: str | None = None

    # Uploaded photos and documents (ADR-025). "local" writes under storage_dir; "gcs" uses a
    # Cloud Storage bucket and stays dormant until storage_bucket is set.
    storage_backend: Literal["local", "gcs"] = "local"
    storage_dir: Path = REPO_ROOT / "var" / "storage"
    storage_bucket: str | None = None

    # "inprocess" runs the outbox in the API process (local, ADR-023). "cloudtasks" creates a
    # Cloud Task after each commit that queued events, calling /internal/outbox/drain (ADR-029);
    # it needs the three settings below. "off" processes nothing (tests).
    outbox_runner: Literal["inprocess", "cloudtasks", "off"] = "inprocess"
    # projects/<project>/locations/<region>/queues/<queue>
    cloud_tasks_queue: str | None = None
    # The API's own public URL; tasks call it, and it is the audience of their OIDC tokens.
    internal_base_url: str | None = None
    # The service account Cloud Tasks and Cloud Scheduler sign their calls as.
    tasks_service_account: str | None = None
    # The decisioning service that holds the lead model (ADR-048). Unset, scoring runs
    # in-process, which needs the service's package installed: local development and tests only.
    decisioning_url: str | None = None

    # Web push (ADR-029) stays dormant until both keys exist. Generate a pair locally with
    # `uv run python -m cornerpin.devtools vapid-keys`.
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:hello@cornerpin.app"

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @property
    def push_enabled(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key)

    @property
    def agent_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_client_id and self.slack_client_secret and self.slack_signing_secret)

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @model_validator(mode="after")
    def _no_local_defaults_outside_local(self) -> Self:
        if self.is_local:
            return self
        problems: list[str] = []
        if self.secret_key == LOCAL_SECRET_KEY:
            problems.append("SECRET_KEY must be set")
        if TURNSTILE_TEST_SECRET_KEY in (self.turnstile_secret_key, self.turnstile_site_key):
            problems.append("Turnstile test keys are for local use only")
        # Salesforce can be connected without any app-level setting, so the key is required
        # whenever the app runs outside local, not only once Slack is configured.
        if self.integrations_key == LOCAL_INTEGRATIONS_KEY:
            problems.append("INTEGRATIONS_KEY must be set")
        if self.storage_backend == "gcs" and not self.storage_bucket:
            problems.append("STORAGE_BUCKET must be set for the gcs storage backend")
        if self.email_backend == "resend" and not self.resend_api_key:
            problems.append("RESEND_API_KEY must be set for the resend email backend")
        if self.inbound_email_domain and not (self.resend_webhook_secret and self.resend_api_key):
            problems.append(
                "RESEND_WEBHOOK_SECRET and RESEND_API_KEY must be set to receive email"
                " at INBOUND_EMAIL_DOMAIN"
            )
        if self.outbox_runner == "cloudtasks" and not (
            self.cloud_tasks_queue and self.internal_base_url and self.tasks_service_account
        ):
            problems.append(
                "CLOUD_TASKS_QUEUE, INTERNAL_BASE_URL and TASKS_SERVICE_ACCOUNT must be set"
                " for the cloudtasks outbox runner"
            )
        if not self.decisioning_url:
            problems.append("DECISIONING_URL must be set: the API image has no model (ADR-048)")
        if problems:
            raise ValueError("; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
