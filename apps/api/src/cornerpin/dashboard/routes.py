"""The owner dashboard's one route (P3-07, ADR-051). Every figure comes from a view in migration
0021, which runs with the reader's rights, so an owner only ever counts their own tenant."""

from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.tenancy import tenant_session
from cornerpin.financing.amortization import add_months

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["dashboard"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Not found, or not your tenant"}
}
LADDER = ("new", "contacted", "engaged", "holding", "won")
BANDS = ("low", "medium", "high", "unscored")
MONTHS = 12

FunnelStageName = Literal["new", "contacted", "engaged", "holding", "won", "lost"]
Band = Literal["low", "medium", "high", "unscored"]


class FunnelStage(BaseModel):
    stage: FunnelStageName
    now: int = Field(description="Leads at this stage today")
    reached: int | None = Field(description="Leads that ever got this far; None for lost")
    conversion: float | None = Field(
        description="Share of the previous stage's leads that got this far, from 0 to 1"
    )


class MonthSales(BaseModel):
    month: date = Field(description="The month's first day")
    sold: int


class PhasePace(BaseModel):
    subdivision_name: str
    phase_name: str
    sold: int
    median_days: float = Field(description="From listing (added to Cornerpin) to sold")


class PhaseInventory(BaseModel):
    subdivision_name: str
    phase_name: str
    available: int
    on_hold: int
    sold: int


class SourceCount(BaseModel):
    source: str
    leads: int


class Outreach(BaseModel):
    sent: int
    replied: int
    handed_off: int


class ScoreBand(BaseModel):
    band: Band
    leads: int


class Dashboard(BaseModel):
    leads: int
    funnel: list[FunnelStage] = Field(description="The ladder in order, then lost")
    sales_by_month: list[MonthSales] = Field(description="The last 12 months, oldest first")
    days_to_sold: list[PhasePace]
    inventory: list[PhaseInventory]
    sources: list[SourceCount] = Field(description="Most leads first")
    outreach: Outreach
    scores: list[ScoreBand] = Field(description="Open leads' latest scores, by band")


def _funnel(session: Session) -> tuple[int, list[FunnelStage]]:
    rows = session.execute(
        text("SELECT stage, reached FROM dashboard_lead_reach WHERE tenant_id = app_tenant_id()")
    ).all()
    now = {stage: sum(1 for r in rows if r.stage == stage) for stage in LADDER}
    funnel: list[FunnelStage] = []
    previous: int | None = None
    for rank, stage in enumerate(LADDER):
        reached = sum(1 for r in rows if r.reached is not None and r.reached >= rank)
        conversion = None if previous is None or previous == 0 else reached / previous
        funnel.append(
            FunnelStage(stage=stage, now=now[stage], reached=reached, conversion=conversion)
        )
        previous = reached
    lost = sum(1 for r in rows if r.stage == "lost")
    funnel.append(FunnelStage(stage="lost", now=lost, reached=None, conversion=None))
    return len(rows), funnel


def _sales_by_month(session: Session, today: date) -> list[MonthSales]:
    sold = {
        row.month: row.sold
        for row in session.execute(
            text(
                "SELECT month, sold FROM dashboard_sales_by_month WHERE tenant_id = app_tenant_id()"
            )
        )
    }
    first = add_months(today.replace(day=1), -(MONTHS - 1))
    months = [add_months(first, i) for i in range(MONTHS)]
    return [MonthSales(month=month, sold=sold.get(month, 0)) for month in months]


@router.get("/dashboard", responses=NOT_FOUND)
def dashboard(tenant_id: UUID, user: SignedInUser) -> Dashboard:
    """The tenant's figures, today. A tenant with nothing yet gets zeros and empty lists."""
    with tenant_session(user, tenant_id) as session:
        leads, funnel = _funnel(session)
        sales = _sales_by_month(session, date.today())
        pace = [
            PhasePace.model_validate(row, from_attributes=True)
            for row in session.execute(
                text(
                    "SELECT subdivision_name, phase_name, sold, median_days"
                    " FROM dashboard_days_to_sold WHERE tenant_id = app_tenant_id()"
                    " ORDER BY subdivision_name, sort_order"
                )
            )
        ]
        inventory = [
            PhaseInventory.model_validate(row, from_attributes=True)
            for row in session.execute(
                text(
                    "SELECT subdivision_name, phase_name, available, on_hold, sold"
                    " FROM dashboard_inventory WHERE tenant_id = app_tenant_id()"
                    " ORDER BY subdivision_name, sort_order"
                )
            )
        ]
        sources = [
            SourceCount.model_validate(row, from_attributes=True)
            for row in session.execute(
                text(
                    "SELECT source, leads FROM dashboard_lead_sources"
                    " WHERE tenant_id = app_tenant_id() ORDER BY leads DESC, source"
                )
            )
        ]
        outreach = session.execute(
            text(
                "SELECT sent, replied, handed_off FROM dashboard_outreach"
                " WHERE tenant_id = app_tenant_id()"
            )
        ).one_or_none()
        bands = {
            row.band: row.leads
            for row in session.execute(
                text("SELECT band, leads FROM dashboard_scores WHERE tenant_id = app_tenant_id()")
            )
        }
    return Dashboard(
        leads=leads,
        funnel=funnel,
        sales_by_month=sales,
        days_to_sold=pace,
        inventory=inventory,
        sources=sources,
        outreach=(
            Outreach.model_validate(outreach, from_attributes=True)
            if outreach
            else Outreach(sent=0, replied=0, handed_off=0)
        ),
        scores=[ScoreBand(band=band, leads=bands.get(band, 0)) for band in BANDS],
    )
