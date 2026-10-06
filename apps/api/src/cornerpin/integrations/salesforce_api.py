"""Talking to one tenant's Salesforce org (P2-08, ADR-041), over the REST API, signed in with
the OAuth 2.0 client credentials flow of an External Client App the owner made in their org.

Records are written by upsert on Cornerpin's own external ID fields, so a retried call updates
the record the first call made instead of making another. `ensure_setup` creates those fields,
and a permission set that lets the app's run-as user write them, when they're missing.

Errors come in two kinds: `Refused` (credentials, permissions or data Salesforce won't accept,
which a retry won't fix) and anything else (busy, down, unreachable), which the outbox
retries."""

import re
import time
from dataclasses import dataclass
from typing import Any, cast

import httpx

API_VERSION = "v62.0"
# Only an org's own My Domain: the secret is never sent anywhere else.
MY_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*\.my\.salesforce\.com$")
TOKEN_SECONDS = 30 * 60  # reused for half an hour; refreshed sooner if Salesforce says so
EXTERNAL_ID = "Cornerpin_Id__c"
PERMISSION_SET = "Cornerpin_Integration"


SALESFORCE_ID = re.compile(r"^[a-zA-Z0-9]{15,18}$")


def _sfid(value: object) -> str:
    """A Salesforce record id, checked before it goes into a query."""
    text = str(value)
    if not SALESFORCE_ID.match(text):
        raise Refused(f"Salesforce returned an unexpected id ({text[:40]})")
    return text


class Refused(Exception):
    """Salesforce won't accept this, and asking again won't change that."""


@dataclass(frozen=True)
class Credentials:
    domain: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class Session:
    access_token: str
    instance_url: str
    org_id: str
    user_id: str
    expires_at: float


@dataclass(frozen=True)
class Field:
    """A custom field Cornerpin needs, as the Tooling API creates it."""

    sobject: str
    name: str  # without __c
    label: str
    metadata: dict[str, Any]

    @property
    def full_name(self) -> str:
        return f"{self.sobject}.{self.name}__c"


def _external_id(sobject: str) -> Field:
    return Field(
        sobject,
        "Cornerpin_Id",
        "Cornerpin ID",
        {
            "type": "Text",
            "length": 36,
            "externalId": True,
            "unique": True,
            "caseSensitive": False,
            "description": "The record's id in Cornerpin. Set by Cornerpin; don't edit.",
        },
    )


FIELDS: tuple[Field, ...] = (
    _external_id("Lead"),
    _external_id("Opportunity"),
    _external_id("Product2"),
    Field("Product2", "Cornerpin_Status", "Lot status", {"type": "Text", "length": 20}),
    Field(
        "Product2",
        "Cornerpin_Price",
        "Lot price",
        {"type": "Currency", "precision": 12, "scale": 2},
    ),
)

_sessions: dict[tuple[str, str], Session] = {}


def _errors(response: httpx.Response) -> str:
    """Salesforce's error messages, briefly."""
    try:
        body: Any = response.json()
    except ValueError:
        return response.text[:300] or str(response.status_code)
    items: list[Any] = cast(list[Any], body) if isinstance(body, list) else [body]
    parts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            entry = cast(dict[str, Any], item)
            code = str(entry.get("errorCode") or entry.get("error") or "")
            message = str(entry.get("message") or entry.get("error_description") or "")
            parts.append(f"{code}: {message}".strip(": "))
    return "; ".join(parts)[:500] or str(response.status_code)


class Org:
    """One tenant's org. `http` is for tests."""

    def __init__(self, credentials: Credentials, http: httpx.Client | None = None) -> None:
        if not MY_DOMAIN.match(credentials.domain):
            raise Refused(f"{credentials.domain} isn't a Salesforce My Domain address")
        self.credentials = credentials
        self._http = http or httpx.Client(timeout=30)

    # --- signing in ------------------------------------------------------------------------

    def session(self, *, fresh: bool = False) -> Session:
        key = (self.credentials.domain, self.credentials.client_id)
        cached = _sessions.get(key)
        if cached and not fresh and cached.expires_at > time.time():
            return cached
        response = self._http.post(
            f"https://{self.credentials.domain}/services/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
            },
        )
        if response.status_code in (400, 401, 403):
            raise Refused(f"Salesforce didn't accept Cornerpin's sign-in ({_errors(response)})")
        response.raise_for_status()
        token: dict[str, Any] = response.json()
        # "id" is https://login.salesforce.com/id/<org id>/<user id>
        org_id, user_id = str(token["id"]).rstrip("/").split("/")[-2:]
        session = Session(
            access_token=token["access_token"],
            instance_url=str(token["instance_url"]).rstrip("/"),
            org_id=org_id,
            user_id=user_id,
            expires_at=time.time() + TOKEN_SECONDS,
        )
        _sessions[key] = session
        return session

    def call(
        self, method: str, path: str, *, json: Any = None, params: dict[str, str] | None = None
    ) -> Any:
        """One REST call, under /services/data/<version>. Signs in again once if the session
        has expired. Returns the parsed body, or None for an empty one."""
        for attempt in range(2):
            session = self.session(fresh=attempt > 0)
            response = self._http.request(
                method,
                f"{session.instance_url}/services/data/{API_VERSION}{path}",
                json=json,
                params=params,
                headers={
                    "Authorization": f"Bearer {session.access_token}",
                    # Lead duplicate rules may alert; they mustn't stop Cornerpin's upserts.
                    "Sforce-Duplicate-Rule-Header": "allowSave=true",
                },
            )
            if response.status_code == 401 and attempt == 0:
                continue
            if response.status_code in (400, 401, 403, 404, 300):
                raise Refused(f"Salesforce refused {method} {path} ({_errors(response)})")
            response.raise_for_status()
            return response.json() if response.content else None
        raise AssertionError("unreachable")

    def query(self, soql: str, *, tooling: bool = False) -> list[dict[str, Any]]:
        answer: dict[str, Any] = self.call(
            "GET", "/tooling/query" if tooling else "/query", params={"q": soql}
        )
        records: list[dict[str, Any]] = answer.get("records", [])
        return records

    # --- writing records ---------------------------------------------------------------------

    def upsert(self, sobject: str, external_id: str, fields: dict[str, Any]) -> str:
        """Create or update the record with this Cornerpin ID; returns its Salesforce id."""
        answer: dict[str, Any] | None = self.call(
            "PATCH", f"/sobjects/{sobject}/{EXTERNAL_ID}/{external_id}", json=fields
        )
        return str((answer or {}).get("id", ""))

    def upsert_many(self, sobject: str, records: list[dict[str, Any]]) -> None:
        """Upsert up to 200 records in one call (sObject Collections)."""
        if not records:
            return
        answer: list[dict[str, Any]] = self.call(
            "PATCH",
            f"/composite/sobjects/{sobject}/{EXTERNAL_ID}",
            json={
                "allOrNone": False,
                "records": [{"attributes": {"type": sobject}, **r} for r in records],
            },
        )
        failed = [r for r in answer if not r.get("success")]
        if failed:
            errors: list[dict[str, Any]] = failed[0].get("errors") or [{}]
            raise Refused(
                f"Salesforce refused {len(failed)} of {len(records)} {sobject} records"
                f" ({errors[0].get('statusCode', '')}: {errors[0].get('message', '')})"
            )

    # --- setting the org up --------------------------------------------------------------------

    def ensure_setup(self) -> list[str]:
        """Create the custom fields Cornerpin writes and a permission set that lets the app's
        run-as user write them, where missing. Returns the fields it created."""
        existing = {
            (row["TableEnumOrId"], row["DeveloperName"])
            for row in self.query(
                "SELECT DeveloperName, TableEnumOrId FROM CustomField"
                " WHERE DeveloperName IN ('Cornerpin_Id', 'Cornerpin_Status', 'Cornerpin_Price')",
                tooling=True,
            )
        }
        created: list[str] = []
        for field in FIELDS:
            if (field.sobject, field.name) not in existing:
                self.call(
                    "POST",
                    "/tooling/sobjects/CustomField",
                    json={
                        "FullName": field.full_name,
                        "Metadata": {"label": field.label, **field.metadata},
                    },
                )
                created.append(field.full_name)

        # SOQL: the only values put in are this module's constant and checked Salesforce ids.
        found = self.query(f"SELECT Id FROM PermissionSet WHERE Name = '{PERMISSION_SET}'")  # noqa: S608
        if found:
            permission_set = _sfid(found[0]["Id"])
        else:
            made: dict[str, Any] = self.call(
                "POST",
                "/sobjects/PermissionSet",
                json={"Name": PERMISSION_SET, "Label": "Cornerpin integration"},
            )
            permission_set = _sfid(made["id"])
        granted = {
            row["Field"]
            for row in self.query(
                f"SELECT Field FROM FieldPermissions WHERE ParentId = '{permission_set}'"  # noqa: S608
            )
        }
        for field in FIELDS:
            if field.full_name not in granted:
                self.call(
                    "POST",
                    "/sobjects/FieldPermissions",
                    json={
                        "ParentId": permission_set,
                        "SobjectType": field.sobject,
                        "Field": field.full_name,
                        "PermissionsRead": True,
                        "PermissionsEdit": True,
                    },
                )
        user = _sfid(self.session().user_id)
        assigned = self.query(
            "SELECT Id FROM PermissionSetAssignment"  # noqa: S608
            f" WHERE PermissionSetId = '{permission_set}' AND AssigneeId = '{user}'"
        )
        if not assigned:
            self.call(
                "POST",
                "/sobjects/PermissionSetAssignment",
                json={"PermissionSetId": permission_set, "AssigneeId": user},
            )
        return created
