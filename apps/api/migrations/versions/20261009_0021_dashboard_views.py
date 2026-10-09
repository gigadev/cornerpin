"""owner dashboard: read-only views over a tenant's leads, lots, outreach and scores

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-09

P3-07 (ADR-002, ADR-051). Each view runs with the reader's own rights (security_invoker), so
the tables' row-level security applies as if the reader queried them: an owner sees only their
tenant. Figures are computed in Postgres, the system of record; Snowflake (P3-08) is analytics
and never serves a page.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The stages a lead climbs, in order; "lost" is off the ladder.
LADDER = "CASE s WHEN 'new' THEN 0 WHEN 'contacted' THEN 1 WHEN 'engaged' THEN 2 WHEN 'holding' THEN 3 WHEN 'won' THEN 4 END"  # noqa: E501

VIEWS = {
    # How far each lead got: the higher of its current stage and every stage it was moved to.
    "dashboard_lead_reach": f"""
        SELECT l.tenant_id, l.id AS lead_id, l.stage::text AS stage,
               greatest(
                 (SELECT {LADDER} FROM (SELECT l.stage::text AS s) cur),
                 (SELECT max({LADDER}) FROM (
                    SELECT e.detail->>'to' AS s FROM lead_events e
                    WHERE e.lead_id = l.id AND e.kind::text = 'stage_changed') moved)
               ) AS reached
        FROM leads l
    """,  # noqa: S608 -- interpolates a fixed SQL fragment
    "dashboard_sales_by_month": """
        SELECT h.tenant_id, date_trunc('month', h.changed_at)::date AS month,
               count(DISTINCT h.lot_id) AS sold
        FROM lot_status_history h
        WHERE h.to_status = 'sold'
        GROUP BY h.tenant_id, date_trunc('month', h.changed_at)
    """,
    # Lots sold now, from being listed (added to Cornerpin) to their latest sale.
    "dashboard_days_to_sold": """
        SELECT l.tenant_id, p.id AS phase_id, s.name AS subdivision_name, p.name AS phase_name,
               p.sort_order, count(*) AS sold,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY
                 extract(epoch FROM sale.at - l.created_at) / 86400) AS median_days
        FROM lots l
        JOIN phases p ON p.id = l.phase_id
        JOIN subdivisions s ON s.id = l.subdivision_id
        JOIN LATERAL (SELECT max(h.changed_at) AS at FROM lot_status_history h
                      WHERE h.lot_id = l.id AND h.to_status = 'sold') sale ON true
        WHERE l.status = 'sold'
        GROUP BY l.tenant_id, p.id, s.name, p.name, p.sort_order
    """,
    "dashboard_inventory": """
        SELECT l.tenant_id, p.id AS phase_id, s.name AS subdivision_name, p.name AS phase_name,
               p.sort_order,
               count(*) FILTER (WHERE l.status = 'available') AS available,
               count(*) FILTER (WHERE l.status = 'on_hold') AS on_hold,
               count(*) FILTER (WHERE l.status = 'sold') AS sold
        FROM lots l
        JOIN phases p ON p.id = l.phase_id
        JOIN subdivisions s ON s.id = l.subdivision_id
        GROUP BY l.tenant_id, p.id, s.name, p.name, p.sort_order
    """,
    "dashboard_lead_sources": """
        SELECT tenant_id, source, count(*) AS leads FROM leads GROUP BY tenant_id, source
    """,
    "dashboard_outreach": """
        SELECT t.tenant_id,
          (SELECT count(*) FROM outreach_messages m WHERE m.tenant_id = t.tenant_id
             AND m.direction = 'outbound' AND m.status = 'sent') AS sent,
          (SELECT count(*) FROM outreach_messages m WHERE m.tenant_id = t.tenant_id
             AND m.direction = 'inbound') AS replied,
          (SELECT count(*) FROM lead_events e WHERE e.tenant_id = t.tenant_id
             AND e.kind::text = 'handoff') AS handed_off
        FROM (SELECT DISTINCT tenant_id FROM leads) t
    """,
    # Each open lead's latest score, in thirds (ADR-047's bands), or unscored.
    "dashboard_scores": """
        SELECT l.tenant_id,
          CASE WHEN r.score IS NULL THEN 'unscored'
               WHEN r.score < 1.0 / 3 THEN 'low'
               WHEN r.score > 2.0 / 3 THEN 'high'
               ELSE 'medium' END AS band,
          count(*) AS leads
        FROM leads l
        LEFT JOIN LATERAL (SELECT score FROM risk_scores r
                           WHERE r.lead_id = l.id AND r.hold_request_id IS NULL
                           ORDER BY r.scored_at DESC, r.id DESC LIMIT 1) r ON true
        WHERE l.stage NOT IN ('won', 'lost')
        GROUP BY l.tenant_id, 2
    """,
}


def upgrade() -> None:
    for name, query in VIEWS.items():
        op.execute(f"CREATE VIEW {name} WITH (security_invoker = true) AS {query}")
        op.execute(f"GRANT SELECT ON {name} TO cornerpin_user")


def downgrade() -> None:
    for name in reversed(list(VIEWS)):
        op.execute(f"DROP VIEW {name}")
