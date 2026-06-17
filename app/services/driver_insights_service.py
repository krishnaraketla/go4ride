"""Driver insights — earnings trends and period comparison."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.enums import RideStatus
from app.models.ride import Ride
from app.schemas.driver_insights import DriverInsightsResponse, DriverTrendPoint
from app.services import driver_earnings_service as earnings_svc

COMPLETED = RideStatus.completed


async def get_driver_insights(
    db: AsyncSession, driver_id: UUID, period: str
) -> DriverInsightsResponse:
    current_start, current_end, prev_start, prev_end = earnings_svc.period_bounds(period)
    settings = get_settings()

    earnings = await earnings_svc.sum_earnings(db, driver_id, current_start, current_end)
    prev_earnings = await earnings_svc.sum_earnings(db, driver_id, prev_start, prev_end)

    comparison_pct: float | None = None
    if prev_earnings > 0:
        comparison_pct = round(float((earnings - prev_earnings) / prev_earnings * 100), 1)

    rides_count = await earnings_svc.count_trips(
        db, driver_id, current_start, current_end, status=COMPLETED
    )
    online_minutes = await earnings_svc.sum_online_minutes(
        db, driver_id, current_start, current_end
    )
    active_minutes = await earnings_svc.sum_active_minutes(
        db, driver_id, current_start, current_end
    )
    online_hours = round(online_minutes / 60, 2)
    active_hours = round(active_minutes / 60, 2)

    earnings_per_hour: Decimal | None = None
    if online_hours > 0:
        earnings_per_hour = (earnings / Decimal(str(online_hours))).quantize(Decimal("0.01"))

    trend = await _build_trend(db, driver_id, period, current_start, current_end)

    return DriverInsightsResponse(
        period=period,
        earnings=earnings,
        rides_count=rides_count,
        online_hours=online_hours,
        active_hours=active_hours,
        earnings_per_hour=earnings_per_hour,
        comparison_pct=comparison_pct,
        trend=trend,
        currency=settings.default_currency,
    )


async def _build_trend(
    db: AsyncSession,
    driver_id: UUID,
    period: str,
    current_start: datetime,
    current_end: datetime,
) -> list[DriverTrendPoint]:
    rows = (
        await db.execute(
            select(Ride.completed_at, Ride.final_fare).where(
                Ride.driver_id == driver_id,
                Ride.status == COMPLETED,
                Ride.completed_at >= current_start,
                Ride.completed_at < current_end,
            )
        )
    ).all()

    if period == "daily":
        counts: dict[int, int] = {}
        earnings_map: dict[int, Decimal] = {}
        for completed_at, final_fare in rows:
            if completed_at is None:
                continue
            hour = completed_at.astimezone(timezone.utc).hour
            counts[hour] = counts.get(hour, 0) + 1
            earnings_map[hour] = earnings_map.get(hour, Decimal("0")) + Decimal(str(final_fare or 0))
        raw = earnings_svc.build_daily_trend(current_start, counts, earnings_map)
    else:
        counts_by_date: dict[date, int] = {}
        earnings_by_date: dict[date, Decimal] = {}
        for completed_at, final_fare in rows:
            if completed_at is None:
                continue
            d = completed_at.astimezone(timezone.utc).date()
            counts_by_date[d] = counts_by_date.get(d, 0) + 1
            earnings_by_date[d] = earnings_by_date.get(d, Decimal("0")) + Decimal(
                str(final_fare or 0)
            )
        if period == "weekly":
            raw = earnings_svc.build_weekly_trend(current_start, counts_by_date, earnings_by_date)
        else:
            raw = earnings_svc.build_monthly_trend(current_start, counts_by_date, earnings_by_date)

    return [DriverTrendPoint(**point) for point in raw]
