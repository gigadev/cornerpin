"""P2-08: Salesforce (ADR-041). A new lead appears in Salesforce after one drain; a stage change
syncs; an approved hold opens an Opportunity; lots sync their status and price; a failed call
retries without a duplicate; a tenant without Salesforce sends nothing. Salesforce is faked:
its HTTP layer against a mock transport, and the flows against an in-memory org."""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cornerpin.core.outbox import drain
from cornerpin.integrations import salesforce, salesforce_api
from cornerpin.integrations.base import Connection
from cornerpin.integrations.salesforce_api import Credentials, Org, Refused, Session

from .conftest import Databases, Listing, TenantData
from .outreach_support import email_of, inquire, lead_of

DOMAIN = "cornerpin-dev.develop.my.salesforce.com"
CREDENTIALS = {"domain": f"https://{DOMAIN}/", "client_id": "3MVG9-consumer-key",
               "client_secret": "consumer-secret-123"}  # fmt: skip


# --- an in-memory org -----------------------------------------------------------------------------


@dataclass
class FakeOrg:
    """Records keyed by (object, Cornerpin ID), as external-ID upserts keep them."""

    records: dict[tuple[str, str], dict[str, Any]] = field(default_factory=lambda: {})
    writes: int = 0
    set_up: int = 0
    refuse: str | None = None  # every call is refused with this
    lose_next_answer: bool = False  # the next write lands, but its answer never arrives
    credentials: list[Credentials] = field(default_factory=lambda: [])

    def session(self, *, fresh: bool = False) -> Session:
        if self.refuse:
            raise Refused(self.refuse)
        return Session("token", f"https://{DOMAIN}", "00Dorg", "005user", 0)

    def ensure_setup(self) -> list[str]:
        self.set_up += 1
        return ["Lead.Cornerpin_Id__c"]

    def _write(self, sobject: str, external_id: str, fields: dict[str, Any]) -> None:
        if self.refuse:
            raise Refused(self.refuse)
        self.writes += 1
        self.records.setdefault((sobject, external_id), {}).update(fields)
        if self.lose_next_answer:
            self.lose_next_answer = False
            raise httpx.ReadTimeout("the answer was lost")

    def upsert(self, sobject: str, external_id: str, fields: dict[str, Any]) -> str:
        self._write(sobject, external_id, fields)
        return "001record"

    def upsert_many(self, sobject: str, records: list[dict[str, Any]]) -> None:
        for record in records:
            fields = dict(record)
            self._write(sobject, fields.pop("Cornerpin_Id__c"), fields)

    def of(self, sobject: str) -> dict[str, dict[str, Any]]:
        return {key: fields for (kind, key), fields in self.records.items() if kind == sobject}


@pytest.fixture
def org(
    db: Databases, tenants: tuple[TenantData, TenantData], monkeypatch: pytest.MonkeyPatch
) -> Iterator[FakeOrg]:
    fake = FakeOrg()

    def org_for(connection: Connection) -> Any:
        fake.credentials.append(
            Credentials(
                connection.settings["domain"],
                connection.secret["client_id"],
                connection.secret["client_secret"],
            )
        )
        return fake

    monkeypatch.setattr(salesforce, "org_for", org_for)
    drain()
    yield fake
    with db.owner.begin() as conn:
        conn.execute(text("DELETE FROM integration_connections WHERE provider = 'salesforce'"))


def connect(owner: TestClient, tenant_id: UUID) -> None:
    sent = owner.post(f"/v1/tenants/{tenant_id}/integrations/salesforce", json=CREDENTIALS)
    assert sent.status_code == 202, sent.text
    assert sent.json()["status"] == "connecting"
    drain()


def salesforce_of(owner: TestClient, tenant_id: UUID) -> dict[str, Any]:
    listed: list[dict[str, Any]] = owner.get(f"/v1/tenants/{tenant_id}/integrations").json()
    return next(i for i in listed if i["provider"] == "salesforce")


def events(db: Databases, kind: str) -> int:
    with db.owner.connect() as conn:
        count: int = conn.execute(
            text("SELECT count(*) FROM outbox WHERE event_type = :k"), {"k": kind}
        ).scalar_one()
    return count


# --- the HTTP layer, against a mock transport --------------------------------------------


@dataclass
class Transport:
    """Answers Salesforce's endpoints from a table; records every request."""

    answers: dict[tuple[str, str], list[httpx.Response]]
    sent: list[httpx.Request] = field(default_factory=lambda: [])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        key = (request.method, request.url.path)
        queue = self.answers.get(key) or self.answers.get((request.method, "*"))
        assert queue, f"unexpected {key}"
        return queue.pop(0) if len(queue) > 1 else queue[0]


def token(access: str = "tok") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": access,
            "instance_url": f"https://{DOMAIN}",
            "id": "https://login.salesforce.com/id/00Dxx0000001gPL/005xx000001X8Uz",
            "token_type": "Bearer",
        },
    )


def org_with(transport: Transport) -> Org:
    salesforce_api._sessions.clear()  # pyright: ignore[reportPrivateUsage]
    return Org(
        Credentials(DOMAIN, "key", "secret"),
        http=httpx.Client(transport=httpx.MockTransport(transport)),
    )


TOKEN_PATH = "/services/oauth2/token"  # noqa: S105 -- a URL path
DATA = f"/services/data/{salesforce_api.API_VERSION}"


def test_only_a_my_domain_gets_the_credentials() -> None:
    with pytest.raises(Refused, match="isn't a Salesforce My Domain"):
        Org(Credentials("attacker.example.com", "key", "secret"))
    with pytest.raises(Refused):
        Org(Credentials("x.my.salesforce.com.attacker.test", "key", "secret"))


def test_signing_in_and_upserting_by_cornerpin_id() -> None:
    transport = Transport(
        {
            ("POST", TOKEN_PATH): [token("first"), token("second")],
            ("PATCH", f"{DATA}/sobjects/Lead/Cornerpin_Id__c/lead-1"): [
                httpx.Response(401, json=[{"errorCode": "INVALID_SESSION_ID", "message": "x"}]),
                httpx.Response(201, json={"id": "00Qxx", "success": True, "created": True}),
            ],
        }
    )
    org = org_with(transport)
    assert org.upsert("Lead", "lead-1", {"LastName": "Rivera"}) == "00Qxx"

    sign_in = parse_qs(transport.sent[0].content.decode())
    assert sign_in == {
        "grant_type": ["client_credentials"],
        "client_id": ["key"],
        "client_secret": ["secret"],
    }
    first, retried = transport.sent[1], transport.sent[3]  # an expired session signs in again
    assert first.headers["authorization"] == "Bearer first"
    assert retried.headers["authorization"] == "Bearer second"
    assert retried.headers["sforce-duplicate-rule-header"] == "allowSave=true"
    assert json.loads(retried.content) == {"LastName": "Rivera"}
    assert org.session().user_id == "005xx000001X8Uz"


def test_refusals_are_told_apart_from_outages() -> None:
    refused = Transport(
        {("POST", TOKEN_PATH): [httpx.Response(400, json={
            "error": "invalid_client", "error_description": "invalid client credentials"})]}
    )  # fmt: skip
    with pytest.raises(Refused, match="invalid_client: invalid client credentials"):
        org_with(refused).session()

    rejected = Transport(
        {
            ("POST", TOKEN_PATH): [token()],
            ("PATCH", "*"): [
                httpx.Response(400, json=[{"errorCode": "INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST",
                                           "message": "Status: bad value"}])
            ],
        }
    )  # fmt: skip
    with pytest.raises(Refused, match="RESTRICTED_PICKLIST: Status: bad value"):
        org_with(rejected).upsert("Lead", "x", {"Status": "Nope"})

    down = Transport({("POST", TOKEN_PATH): [token()], ("PATCH", "*"): [httpx.Response(503)]})
    with pytest.raises(httpx.HTTPStatusError):  # not Refused: the outbox retries it
        org_with(down).upsert("Lead", "x", {})

    partial = Transport(
        {
            ("POST", TOKEN_PATH): [token()],
            ("PATCH", f"{DATA}/composite/sobjects/Product2/Cornerpin_Id__c"): [
                httpx.Response(200, json=[
                    {"success": True},
                    {"success": False, "errors": [{"statusCode": "FIELD_INTEGRITY_EXCEPTION",
                                                   "message": "bad price"}]},
                ])
            ],
        }
    )  # fmt: skip
    with pytest.raises(Refused, match="refused 1 of 2 Product2 records"):
        org_with(partial).upsert_many("Product2", [{"Name": "a"}, {"Name": "b"}])


def test_setup_creates_only_what_is_missing() -> None:
    def query(request: httpx.Request) -> httpx.Response:
        soql = request.url.params["q"]
        if "FROM CustomField" in soql:  # Lead's ID field is already there
            records = [{"DeveloperName": "Cornerpin_Id", "TableEnumOrId": "Lead"}]
        elif "FROM FieldPermissions" in soql:
            records = [{"Field": "Lead.Cornerpin_Id__c"}]
        elif "FROM PermissionSet " in soql:
            records = [{"Id": "0PSxx0000000001"}]
        else:
            records = []  # not yet assigned
        return httpx.Response(200, json={"records": records})

    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.path == TOKEN_PATH:
            return token()
        if request.method == "GET":
            return query(request)
        return httpx.Response(201, json={"id": "0xxNEW0000000001", "success": True})

    salesforce_api._sessions.clear()  # pyright: ignore[reportPrivateUsage]
    org = Org(
        Credentials(DOMAIN, "k", "s"), http=httpx.Client(transport=httpx.MockTransport(answer))
    )
    created = org.ensure_setup()

    assert created == [
        "Opportunity.Cornerpin_Id__c",
        "Product2.Cornerpin_Id__c",
        "Product2.Cornerpin_Status__c",
        "Product2.Cornerpin_Price__c",
    ]
    posts = [(r.url.path.rsplit("/", 1)[-1], json.loads(r.content)) for r in sent
             if r.method == "POST" and r.url.path != TOKEN_PATH]  # fmt: skip
    assert [kind for kind, _ in posts] == ["CustomField"] * 4 + ["FieldPermissions"] * 4 + [
        "PermissionSetAssignment"
    ]
    assert posts[0][1]["Metadata"]["externalId"] is True
    assert posts[-1][1] == {"PermissionSetId": "0PSxx0000000001", "AssigneeId": "005xx000001X8Uz"}


# --- connecting ----------------------------------------------------------------------------


def test_an_owner_connects_salesforce_and_the_lots_go_across(
    org: FakeOrg, alpha_owner: TestClient, listing: Listing, db: Databases
) -> None:
    tenant = listing.tenant.tenant_id
    bad = alpha_owner.post(
        f"/v1/tenants/{tenant}/integrations/salesforce",
        json={**CREDENTIALS, "domain": "login.attacker.test"},
    )
    assert bad.status_code == 422

    connect(alpha_owner, tenant)
    assert org.set_up == 1
    assert org.credentials[-1] == Credentials(DOMAIN, "3MVG9-consumer-key", "consumer-secret-123")
    now = salesforce_of(alpha_owner, tenant)
    assert {k: now[k] for k in ("status", "enabled", "account")} == {
        "status": "connected",
        "enabled": True,
        "account": DOMAIN,
    }
    assert "consumer-secret" not in json.dumps(now)

    products = org.of("Product2")
    sold = products[listing.sold]
    shown = ("Name", "IsActive", "Cornerpin_Status__c", "Cornerpin_Price__c")
    assert {k: sold[k] for k in shown} == {
        "Name": "Lot 2, Buyers",
        "IsActive": True,
        "Cornerpin_Status__c": "sold",
        "Cornerpin_Price__c": 90000.0,
    }  # fmt: skip
    assert products[listing.unpublished]["IsActive"] is False


def test_refused_credentials_show_on_the_page(
    org: FakeOrg, alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    org.refuse = "Salesforce didn't accept Cornerpin's sign-in (invalid_client: bad key)"
    connect(alpha_owner, tenants[0].tenant_id)
    now = salesforce_of(alpha_owner, tenants[0].tenant_id)
    assert (now["status"], now["error"]) == ("failed", org.refuse)
    assert org.records == {}


# --- leads, holds and lots ------------------------------------------------------------------


def test_a_new_lead_appears_after_one_drain_and_follows_its_stage(
    org: FakeOrg, alpha_owner: TestClient, buyer: TestClient, listing: Listing, db: Databases
) -> None:
    tenant = listing.tenant.tenant_id
    connect(alpha_owner, tenant)

    inquire(buyer, listing, allow_email=False)
    drain()
    lead_id = str(lead_of(db, listing, email_of(buyer)))
    lead = org.of("Lead")[lead_id]
    assert {k: lead[k] for k in ("FirstName", "LastName", "Company", "Email", "Status")} == {
        "FirstName": "Pat",
        "LastName": "Buyer",
        "Company": "Individual",
        "Email": email_of(buyer),
        "Status": "Open - Not Contacted",
    }

    base = f"/v1/tenants/{tenant}/leads/{lead_id}"
    assert alpha_owner.patch(base, json={"stage": "engaged"}).status_code == 200
    drain()
    assert org.of("Lead")[lead_id]["Status"] == "Working - Contacted"
    assert alpha_owner.patch(base, json={"stage": "lost"}).status_code == 200
    drain()
    assert org.of("Lead")[lead_id]["Status"] == "Closed - Not Converted"


def test_an_approved_hold_opens_an_opportunity_and_the_lot_follows(
    org: FakeOrg, alpha_owner: TestClient, buyer: TestClient, listing: Listing, db: Databases
) -> None:
    tenant = listing.tenant.tenant_id
    connect(alpha_owner, tenant)
    held = buyer.post(f"/v1/lots/{listing.available}/hold-requests", json={"name": "Pat Buyer"})
    assert held.status_code == 201, held.text
    hold_id = held.json()["id"]
    decided = alpha_owner.post(
        f"/v1/tenants/{tenant}/hold-requests/{hold_id}/decision", json={"decision": "approve"}
    )
    assert decided.status_code == 200, decided.text
    drain()

    opportunity = org.of("Opportunity")[hold_id]
    assert opportunity["Name"] == "Hold: Lot 1, Buyers (Pat Buyer)"
    assert (opportunity["StageName"], opportunity["Amount"]) == ("Negotiation/Review", 90000.0)
    lot = org.of("Product2")[listing.available]
    assert lot["Cornerpin_Status__c"] == "on hold"

    changed = alpha_owner.patch(f"/v1/tenants/{tenant}/lots/{listing.available}",
                                json={"price": 87500})  # fmt: skip
    assert changed.status_code == 200, changed.text
    drain()
    assert org.of("Product2")[listing.available]["Cornerpin_Price__c"] == float(Decimal(87500))


def test_a_lost_answer_retries_without_a_duplicate(
    org: FakeOrg, alpha_owner: TestClient, buyer: TestClient, listing: Listing, db: Databases
) -> None:
    connect(alpha_owner, listing.tenant.tenant_id)
    org.lose_next_answer = True  # the Lead is written, but Cornerpin never hears so
    inquire(buyer, listing, allow_email=False)
    drain()
    with db.owner.begin() as conn:  # the retry's back-off, skipped
        failed = (
            conn.execute(
                text(
                    "UPDATE outbox SET available_at = now() WHERE processed_at IS NULL"
                    " AND event_type = 'integrations.deliver_activity' RETURNING last_error"
                )
            )
            .scalars()
            .all()
        )
    assert failed == ["the answer was lost"]
    drain()

    lead_id = str(lead_of(db, listing, email_of(buyer)))
    assert [key for key in org.of("Lead") if key == lead_id] == [lead_id]  # one Lead
    assert org.writes == len(org.of("Product2")) + 2  # the lots, then the Lead twice


def test_a_tenant_without_salesforce_sends_nothing(
    org: FakeOrg, alpha_owner: TestClient, buyer: TestClient, listing: Listing, db: Databases
) -> None:
    tenant = listing.tenant.tenant_id
    lots_queued = events(db, "integrations.lot_changed")
    inquire(buyer, listing, allow_email=False)
    alpha_owner.patch(f"/v1/tenants/{tenant}/lots/{listing.available}", json={"price": 91000})
    drain()
    assert events(db, "integrations.lot_changed") == lots_queued
    assert org.records == {}

    connect(alpha_owner, tenant)
    assert alpha_owner.patch(f"/v1/tenants/{tenant}/integrations/salesforce",
                             json={"enabled": False}).status_code == 200  # fmt: skip
    writes = org.writes
    alpha_owner.patch(f"/v1/tenants/{tenant}/lots/{listing.available}", json={"price": 92000})
    drain()
    assert org.writes == writes  # switched off

    assert alpha_owner.delete(f"/v1/tenants/{tenant}/integrations/salesforce").status_code == 204
    assert salesforce_of(alpha_owner, tenant)["status"] == "not_connected"


def test_data_salesforce_refuses_marks_the_connection_failed(
    org: FakeOrg, alpha_owner: TestClient, buyer: TestClient, listing: Listing
) -> None:
    connect(alpha_owner, listing.tenant.tenant_id)
    org.refuse = "Salesforce refused PATCH /sobjects/Lead (INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST)"
    inquire(buyer, listing, allow_email=False)
    drain()
    now = salesforce_of(alpha_owner, listing.tenant.tenant_id)
    assert (now["status"], now["error"]) == ("failed", org.refuse)
