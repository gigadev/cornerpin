"""Salesforce (P2-08, ADR-041): each lead is a Salesforce Lead, kept up to date as its stage
changes; an approved hold is an Opportunity; each lot is a Product with its status and price.
Every record is upserted on its Cornerpin ID, so retries never duplicate it.

Connecting checks the owner's credentials, sets the org up (fields and a permission set, where
missing) and sends every lot across, all in the worker; the connection is usable only after."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.integrations.base import Activity, Broken, Connection, Lot, lots
from cornerpin.integrations.crypto import unseal
from cornerpin.integrations.salesforce_api import Credentials, Org, Refused

PROVIDER = "salesforce"
BATCH = 200  # records per sObject Collections call
# A new org's standard Lead Status values. A converted status can't be set through the API, so
# a won lead stays "Working"; its Opportunity says it was won.
LEAD_STATUS = {
    "new": "Open - Not Contacted",
    "contacted": "Working - Contacted",
    "engaged": "Working - Contacted",
    "holding": "Working - Contacted",
    "won": "Working - Contacted",
    "lost": "Closed - Not Converted",
}
LEAD_SOURCE = "Web"
OPPORTUNITY_STAGE = "Negotiation/Review"
HOLD_CLOSE_DAYS = 30
LOT_STATUS = {"available": "available", "on_hold": "on hold", "sold": "sold"}


def org_for(connection: Connection) -> Org:
    return Org(
        Credentials(
            domain=connection.settings["domain"],
            client_id=connection.secret["client_id"],
            client_secret=connection.secret["client_secret"],
        )
    )


# --- what Salesforce gets ---------------------------------------------------------------------


def split_name(name: str, email: str) -> tuple[str | None, str]:
    """(FirstName, LastName). Salesforce needs a last name; the email stands in for none."""
    parts = name.split()
    if not parts:
        return None, email.split("@")[0][:80]
    if len(parts) == 1:
        return None, parts[0][:80]
    return " ".join(parts[:-1])[:40], parts[-1][:80]


def lead_fields(activity: Activity) -> dict[str, Any]:
    first, last = split_name(activity.name, activity.email)
    return {
        "FirstName": first,
        "LastName": last,
        "Company": "Individual",
        "Email": activity.email,
        "Phone": activity.phone,
        "Status": LEAD_STATUS[activity.stage],
        "LeadSource": LEAD_SOURCE,
        "Description": f"From Cornerpin: {activity.lead_url}",
    }


def opportunity_fields(activity: Activity) -> dict[str, Any]:
    decided = activity.decided_at or datetime.now(UTC)
    return {
        "Name": f"Hold: {activity.lot or 'a lot'} ({activity.buyer})"[:120],
        "StageName": OPPORTUNITY_STAGE,
        "CloseDate": (decided + timedelta(days=HOLD_CLOSE_DAYS)).date().isoformat(),
        "Amount": float(activity.lot_price) if activity.lot_price is not None else None,
        "LeadSource": LEAD_SOURCE,
        "Description": f"Hold approved in Cornerpin. The lead: {activity.lead_url}",
    }


def product_fields(lot: Lot) -> dict[str, Any]:
    return {
        "Cornerpin_Id__c": str(lot.id),
        "Name": lot.name[:255],
        "ProductCode": f"{lot.slug}/{lot.number}"[:255],
        "IsActive": lot.public,
        "Description": (
            f"{'Lot and home' if lot.listing_type == 'lot_and_home' else 'Land only'}"
            f"{f', {lot.acreage.normalize()} acres' if lot.acreage is not None else ''}."
            f"{f' {lot.url}' if lot.public else ' Not published.'}"
        ),
        "Cornerpin_Status__c": LOT_STATUS.get(lot.status, lot.status),
        "Cornerpin_Price__c": float(lot.price) if lot.price is not None else None,
    }


class SalesforceAdapter:
    provider = PROVIDER

    def wants(self, activity: Activity) -> bool:
        return True  # every lead change updates the Lead

    def deliver(self, connection: Connection, activity: Activity) -> None:
        org = org_for(connection)
        try:
            org.upsert("Lead", str(activity.lead_id), lead_fields(activity))
            if activity.kind == "hold_approved" and activity.hold_request_id:
                org.upsert(
                    "Opportunity", str(activity.hold_request_id), opportunity_fields(activity)
                )
        except Refused as exc:
            raise Broken(str(exc)) from exc

    def sync_lots(self, connection: Connection, changed: list[Lot]) -> None:
        try:
            send_lots(org_for(connection), changed)
        except Refused as exc:
            raise Broken(str(exc)) from exc


def send_lots(org: Org, changed: list[Lot]) -> None:
    for start in range(0, len(changed), BATCH):
        org.upsert_many("Product2", [product_fields(lot) for lot in changed[start : start + BATCH]])


# --- connecting ---------------------------------------------------------------------------------


def connect(session: Session, tenant_id: UUID) -> None:
    """Sign in with the credentials the owner gave, set the org up and send the lots. A
    connection removed or replaced in the meantime is left alone."""
    row = session.execute(
        text(
            "SELECT id, settings, secret FROM integration_connections"
            " WHERE tenant_id = :t AND provider = 'salesforce' AND status = 'connecting'"
        ),
        {"t": tenant_id},
    ).one_or_none()
    if row is None or row.secret is None:
        return
    connection = Connection(
        id=row.id,
        tenant_id=tenant_id,
        provider=PROVIDER,
        settings=row.settings,
        secret=unseal(tenant_id, PROVIDER, bytes(row.secret)),
    )
    try:
        org = org_for(connection)
        signed_in = org.session(fresh=True)
        created = org.ensure_setup()
        send_lots(org, lots(session, tenant_id=tenant_id))
    except Refused as exc:
        session.execute(
            text(
                "UPDATE integration_connections SET status = 'failed', error = left(:e, 500)"
                " WHERE id = :id"
            ),
            {"id": row.id, "e": str(exc)},
        )
        return
    settings = {
        **row.settings,
        "org_id": signed_in.org_id,
        "user_id": signed_in.user_id,
        "fields_created": created,
    }
    session.execute(
        text(
            "UPDATE integration_connections SET status = 'connected', enabled = true,"
            " error = NULL, settings = CAST(:s AS jsonb) WHERE id = :id"
        ),
        {"id": row.id, "s": json.dumps(settings)},
    )
