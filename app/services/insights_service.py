from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.exceptions import bad_request
from app.models.enums import RideStatus
from app.models.ride import Ride, RideType
from app.schemas.insights import DistributionItem, InsightsResponse, TrendPoint

COMPLETED = RideStatus.completed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _period_bounds(period: str, now: datetime | None = None) -> tuple[datetime, datetime, datetime, datetime]:
    """Return (current_start, current_end, prev_start, prev_end) in UTC."""
    now = now or _utc_now()
    today = now.date()
    if period == "weekly":
        # Monday of current week (ISO)
        start_of_week = today - timedelta(days=today.weekday())
        current_start = datetime.combine(start_of_week, datetime.min.time(), tzinfo=timezone.utc)
        current_end = current_start + timedelta(days=7)
        prev_start = current_start - timedelta(days=7)
        prev_end = current_start
    elif period == "monthly":
        current_start = datetime(today.year, today.month, 1, tzinfo=timezone.utc)
        if today.month == 12:
            current_end = datetime(today.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            current_end = datetime(today.year, today.month + 1, 1, tzinfo=timezone.utc)
        if today.month == 1:
            prev_start = datetime(today.year - 1, 12, 1, tzinfo=timezone.utc)
        else:
            prev_start = datetime(today.year, today.month - 1, 1, tzinfo=timezone.utc)
        prev_end = current_start
    else:
        raise bad_request("period must be weekly or monthly", "INVALID_PERIOD")
    return current_start, current_end, prev_start, prev_end


def _build_trend(period: str, current_start: datetime, counts_by_date: dict[date, int]) -> list[TrendPoint]:
    points: list[TrendPoint] = []
    if period == "weekly":
        labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, label in enumerate(labels):
            d = (current_start.date() + timedelta(days=i))
            points.append(
                TrendPoint(
                    label=label,
                    date=d.isoformat(),
                    ride_count=counts_by_date.get(d, 0),
                )
            )
    else:
        # monthly: days 1..N in current month
        start_date = current_start.date()
        if start_date.month == 12:
            end_date = date(start_date.year + 1, 1, 1)
        else:
            end_date = date(start_date.year, start_date.month + 1, 1)
        day = start_date
        while day < end_date:
            points.append(
                TrendPoint(
                    label=str(day.day),
                    date=day.isoformat(),
                    ride_count=counts_by_date.get(day, 0),
                )
            )
            day += timedelta(days=1)
    return points


async def get_insights(db: AsyncSession, rider_id, period: str) -> InsightsResponse:
    current_start, current_end, prev_start, prev_end = _period_bounds(period)
    settings = get_settings()

    base_current = (
        Ride.rider_id == rider_id,
        Ride.status == COMPLETED,
        Ride.completed_at >= current_start,
        Ride.completed_at < current_end,
    )
    agg = await db.execute(
        select(
            func.count(Ride.id),
            func.coalesce(func.sum(Ride.distance_km), 0),
            func.coalesce(func.sum(Ride.final_fare), 0),
        ).where(*base_current)
    )
    rides_count, total_km, total_spend = agg.one()

    prev_count = (
        await db.execute(
            select(func.count(Ride.id)).where(
                Ride.rider_id == rider_id,
                Ride.status == COMPLETED,
                Ride.completed_at >= prev_start,
                Ride.completed_at < prev_end,
            )
        )
    ).scalar() or 0

    comparison_pct: float | None = None
    if prev_count > 0:
        comparison_pct = round((rides_count - prev_count) / prev_count * 100, 1)

    # trend buckets
    rides_in_period = (
        await db.execute(
            select(Ride.completed_at).where(*base_current)
        )
    ).scalars().all()
    counts_by_date: dict[date, int] = {}
    for completed_at in rides_in_period:
        if completed_at:
            d = completed_at.astimezone(timezone.utc).date()
            counts_by_date[d] = counts_by_date.get(d, 0) + 1

    trend = _build_trend(period, current_start, counts_by_date)

    # distribution by ride type
    dist_rows = (
        await db.execute(
            select(Ride.ride_type_id, func.count(Ride.id))
            .where(*base_current)
            .group_by(Ride.ride_type_id)
        )
    ).all()
    type_ids = [row[0] for row in dist_rows]
    types_map: dict = {}
    if type_ids:
        types_result = await db.execute(select(RideType).where(RideType.id.in_(type_ids)))
        types_map = {t.id: t for t in types_result.scalars().all()}

    total_for_pct = rides_count or 1
    distribution = [
        DistributionItem(
            slug=types_map[rt_id].slug,
            name=types_map[rt_id].name,
            count=cnt,
            percent=round(cnt / total_for_pct * 100, 1),
        )
        for rt_id, cnt in dist_rows
        if rt_id in types_map
    ]

    return InsightsResponse(
        period=period,
        rides_count=rides_count,
        total_km=Decimal(str(total_km)),
        total_spend=Decimal(str(total_spend)),
        currency=settings.default_currency,
        trend=trend,
        comparison_pct=comparison_pct,
        distribution=distribution,
    )
