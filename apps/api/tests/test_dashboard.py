"""P3-07: the owner dashboard (ADR-051). Every figure is checked against the raw tables."""

from collections import Counter
from collections.abc import Callable
from datetime import date
from statistics import median
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from cornerpin.core.auth import service
from cornerpin.core.auth.deps import SESSION_COOKIE
from cornerpin.core.db import user_session
from cornerpin.core.outbox import drain
from cornerpin.financing.amortization import add_months
from cornerpin.main import create_app
from cornerpin.seed import DEMO_TENANT_ID

from .conftest import Databases, TenantData

LADDER = ("new", "contacted", "engaged", "holding", "won")
URL = f"/v1/tenants/{DEMO_TENANT_ID}"


def _rows(db: Databases, sql: str) -> list[Any]:
    with db.owner.connect() as conn:
        return list(conn.execute(text(sql), {"t": DEMO_TENANT_ID}).all())


def _make_activity(
    db: Databases, client_for: Callable[[str], TestClient], owner: TestClient
) -> None:
    """Three questions on the demo tenant; one lead won and one lost after moving up."""
    lots = _rows(
        db,
        "SELECT id FROM lots WHERE tenant_id = :t AND status = 'available' AND published"
        " ORDER BY number LIMIT 3",
    )
    for i, lot in enumerate(lots):
        buyer = client_for(f"dashboard-{i}-{uuid4().hex[:6]}@example.test")
        sent = buyer.post(
            f"/v1/lots/{lot.id}/inquiries",
            json={"name": f"Dash {i}", "message": "Still for sale?", "contact": {"email": True}},
        )
        assert sent.status_code == 201, sent.text
    leads = owner.get(f"{URL}/leads").json()["leads"]
    won, lost = leads[0]["id"], leads[1]["id"]
    for stage in ("contacted", "engaged", "won"):
        assert owner.patch(f"{URL}/leads/{won}", json={"stage": stage}).status_code == 200
    for stage in ("contacted", "lost"):
        assert owner.patch(f"{URL}/leads/{lost}", json={"stage": stage}).status_code == 200
    drain()


def test_every_figure_matches_the_tables(
    db: Databases, demo_owner: TestClient, client_for: Callable[[str], TestClient]
) -> None:
    _make_activity(db, client_for, demo_owner)
    found = demo_owner.get(f"{URL}/dashboard")
    assert found.status_code == 200, found.text
    board = found.json()

    # Leads, and how far each got: its current stage or the highest it was moved to.
    leads = _rows(db, "SELECT id, stage::text AS stage FROM leads WHERE tenant_id = :t")
    moves = _rows(
        db,
        "SELECT lead_id, detail->>'to' AS stage FROM lead_events"
        " WHERE tenant_id = :t AND kind::text = 'stage_changed'",
    )
    rank = {stage: i for i, stage in enumerate(LADDER)}
    reached: dict[Any, int] = {}
    for lead in leads:
        reached[lead.id] = rank.get(lead.stage, -1)
    for move in moves:
        reached[move.lead_id] = max(reached[move.lead_id], rank.get(move.stage, -1))
    now = Counter(lead.stage for lead in leads)
    assert board["leads"] == len(leads) >= 3
    funnel = {row["stage"]: row for row in board["funnel"]}
    for stage, position in rank.items():
        assert funnel[stage]["now"] == now[stage]
        assert funnel[stage]["reached"] == sum(1 for r in reached.values() if r >= position)
    assert funnel["lost"]["now"] == now["lost"] >= 1
    assert funnel["won"]["reached"] >= 1
    assert funnel["contacted"]["conversion"] == (
        funnel["contacted"]["reached"] / funnel["new"]["reached"]
    )

    # Sales by month: the last 12 months, each against the history.
    first = add_months(date.today().replace(day=1), -11)
    sales = _rows(
        db,
        "SELECT date_trunc('month', changed_at)::date AS month, count(DISTINCT lot_id) AS sold"
        " FROM lot_status_history WHERE tenant_id = :t AND to_status = 'sold' GROUP BY 1",
    )
    expected = {row.month: row.sold for row in sales}
    months = board["sales_by_month"]
    assert [m["month"] for m in months] == [add_months(first, i).isoformat() for i in range(12)]
    assert all(m["sold"] == expected.get(date.fromisoformat(m["month"]), 0) for m in months)

    # Days from listing to sold, by phase.
    sold = _rows(
        db,
        "SELECT p.name, extract(epoch FROM (SELECT max(h.changed_at) FROM lot_status_history h"
        " WHERE h.lot_id = l.id AND h.to_status = 'sold') - l.created_at) / 86400 AS days"
        " FROM lots l JOIN phases p ON p.id = l.phase_id"
        " WHERE l.tenant_id = :t AND l.status = 'sold'",
    )
    by_phase: dict[str, list[float]] = {}
    for row in sold:
        by_phase.setdefault(row.name, []).append(float(row.days))
    pace = {row["phase_name"]: row for row in board["days_to_sold"]}
    assert set(pace) == set(by_phase)
    for phase, days in by_phase.items():
        assert pace[phase]["sold"] == len(days)
        assert abs(pace[phase]["median_days"] - median(days)) < 0.01

    # Inventory by phase and status.
    inventory = _rows(
        db,
        "SELECT p.name, l.status::text AS status, count(*) AS n FROM lots l"
        " JOIN phases p ON p.id = l.phase_id WHERE l.tenant_id = :t GROUP BY 1, 2",
    )
    counts = {(row.name, row.status): row.n for row in inventory}
    for phase in board["inventory"]:
        for status in ("available", "on_hold", "sold"):
            assert phase[status] == counts.get((phase["phase_name"], status), 0)

    # Lead sources, outreach and scores.
    sources = _rows(db, "SELECT source, count(*) AS n FROM leads WHERE tenant_id = :t GROUP BY 1")
    assert {s["source"]: s["leads"] for s in board["sources"]} == {r.source: r.n for r in sources}
    [outreach] = _rows(
        db,
        "SELECT (SELECT count(*) FROM outreach_messages WHERE tenant_id = :t"
        "   AND direction = 'outbound' AND status = 'sent') AS sent,"
        " (SELECT count(*) FROM outreach_messages WHERE tenant_id = :t"
        "   AND direction = 'inbound') AS replied,"
        " (SELECT count(*) FROM lead_events WHERE tenant_id = :t"
        "   AND kind::text = 'handoff') AS handed_off",
    )
    assert board["outreach"] == {
        "sent": outreach.sent,
        "replied": outreach.replied,
        "handed_off": outreach.handed_off,
    }
    latest = _rows(
        db,
        "SELECT (SELECT score FROM risk_scores r WHERE r.lead_id = l.id"
        "  AND r.hold_request_id IS NULL ORDER BY scored_at DESC, id DESC LIMIT 1) AS score"
        " FROM leads l WHERE l.tenant_id = :t AND l.stage NOT IN ('won', 'lost')",
    )

    def band(score: Any) -> str:
        if score is None:
            return "unscored"
        return "low" if score < 1 / 3 else "high" if score > 2 / 3 else "medium"

    expected_bands = Counter(band(row.score) for row in latest)
    assert {b["band"]: b["leads"] for b in board["scores"]} == {
        name: expected_bands[name] for name in ("low", "medium", "high", "unscored")
    }


def test_the_seeded_demo_has_a_believable_history(db: Databases, demo: None) -> None:
    sales = _rows(
        db,
        "SELECT DISTINCT date_trunc('month', changed_at) AS month FROM lot_status_history"
        " WHERE tenant_id = :t AND to_status = 'sold'",
    )
    assert len(sales) >= 10
    listed = _rows(
        db,
        "SELECT min(changed_at) AS first FROM lot_status_history"
        " WHERE tenant_id = :t AND to_status = 'available'",
    )
    assert (date.today() - listed[0].first.date()).days >= 590


def test_a_tenant_with_nothing_yet_gets_zeros_and_empty_lists(db: Databases) -> None:
    tenant, owner = uuid4(), f"owner-{uuid4().hex[:8]}@empty.test"
    with db.owner.begin() as conn:
        conn.execute(text("INSERT INTO tenants (id, name) VALUES (:t, 'Empty Co.')"), {"t": tenant})
        user = conn.execute(
            text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": owner}
        ).scalar_one()
        conn.execute(
            text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, 'owner')"),
            {"t": tenant, "u": user},
        )
    with TestClient(create_app()) as client:
        signed_in = service.sign_in_verified_email(owner, None, "/app", "pytest")
        client.cookies.set(SESSION_COOKIE, signed_in.session_token)
        found = client.get(f"/v1/tenants/{tenant}/dashboard")
    assert found.status_code == 200, found.text
    board = found.json()
    assert board["leads"] == 0
    assert all(stage["now"] == 0 for stage in board["funnel"])
    assert all(stage["conversion"] is None for stage in board["funnel"])
    assert [m["sold"] for m in board["sales_by_month"]] == [0] * 12
    assert board["days_to_sold"] == board["inventory"] == board["sources"] == []
    assert board["outreach"] == {"sent": 0, "replied": 0, "handed_off": 0}
    assert all(b["leads"] == 0 for b in board["scores"])


def test_the_views_show_an_owner_only_their_tenant(
    db: Databases, tenants: tuple[TenantData, TenantData], demo: None
) -> None:
    alpha, _ = tenants
    views = (
        "dashboard_lead_reach",
        "dashboard_sales_by_month",
        "dashboard_days_to_sold",
        "dashboard_inventory",
        "dashboard_lead_sources",
        "dashboard_outreach",
        "dashboard_scores",
    )
    with user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session:
        for view in views:
            others = session.execute(
                text(f"SELECT count(*) FROM {view} WHERE tenant_id <> :t"),  # noqa: S608
                {"t": alpha.tenant_id},
            ).scalar_one()
            assert others == 0, view
        mine = session.execute(text("SELECT count(*) FROM dashboard_inventory")).scalar_one()
        assert mine > 0


def test_another_tenants_dashboard_is_not_found(alpha_owner: TestClient, demo: None) -> None:
    assert alpha_owner.get(f"{URL}/dashboard").status_code == 404
