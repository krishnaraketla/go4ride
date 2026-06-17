"""Driver earnings and period aggregation."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import bad_request
from app.models.driver_session import DriverOnlineSession
from app.models.enums import RideStatus
from app.models.ride import Ride

COMPLETED = RideStatus.completed
CANCELLED = RideStatus.cancelled


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def period_bounds(
    period: str, now: datetime | None = None
) -> tuple[datetime, datetime, datetime, datetime]:
    """Return (current_start, current_end, prev_start, prev_end) in UTC."""
    now = now or _utc_now()
    today = now.date()
    if period == "daily":
        current_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        current_end = now
        prev_start = current_start - timedelta(days=1)
        prev_end = current_start
    elif period == "weekly":
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
        raise bad_request("period must be daily, weekly, or monthly", "INVALID_PERIOD")
    return current_start, current_end, prev_start, prev_end


def today_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or _utc_now()
    start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
    return start, now


def week_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    start, end, _, _ = period_bounds("weekly", now)
    return start, end


def month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    start, end, _, _ = period_bounds("monthly", now)
    return start, end


async def sum_earnings(
    db: AsyncSession, driver_id: UUID, start: datetime, end: datetime
) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(Ride.final_fare), 0)).where(
            Ride.driver_id == driver_id,
            Ride.status == COMPLETED,
            Ride.completed_at >= start,
            Ride.completed_at < end,
        )
    )
    return Decimal(str(result.scalar() or 0))


async def count_trips(
    db: AsyncSession,
    driver_id: UUID,
    start: datetime,
    end: datetime,
    *,
    status: RideStatus | None = None,
) -> int:
    conditions = [
        Ride.driver_id == driver_id,
        Ride.completed_at >= start,
        Ride.completed_at < end,
    ]
    if status is not None:
        conditions.append(Ride.status == status)
        if status == CANCELLED:
            conditions = [
                Ride.driver_id == driver_id,
                Ride.cancelled_at >= start,
                Ride.cancelled_at < end,
                Ride.status == CANCELLED,
            ]
    else:
        conditions.append(Ride.status == COMPLETED)
    result = await db.execute(select(func.count()).select_from(Ride).where(*conditions))
    return result.scalar() or 0


async def count_trips_today(db: AsyncSession, driver_id: UUID) -> int:
    start, end = today_bounds()
    return await count_trips(db, driver_id, start, end, status=COMPLETED)


async def sum_active_minutes(
    db: AsyncSession, driver_id: UUID, start: datetime, end: datetime
) -> float:
    result = await db.execute(
        select(func.coalesce(func.sum(Ride.duration_min), 0)).where(
            Ride.driver_id == driver_id,
            Ride.status == COMPLETED,
            Ride.completed_at >= start,
            Ride.completed_at < end,
        )
    )
    return float(result.scalar() or 0)


async def sum_online_minutes(
    db: AsyncSession, driver_id: UUID, start: datetime, end: datetime
) -> float:
    now = _utc_now()
    result = await db.execute(
        select(DriverOnlineSession).where(
            DriverOnlineSession.driver_id == driver_id,
            DriverOnlineSession.started_at < end,
            (DriverOnlineSession.ended_at.is_(None)) | (DriverOnlineSession.ended_at > start),
        )
    )
    sessions = result.scalars().all()
    total_seconds = 0.0
    for session in sessions:
        session_start = max(session.started_at, start)
        session_end = min(session.ended_at or now, end)
        if session_end > session_start:
            total_seconds += (session_end - session_start).total_seconds()
    return total_seconds / 60.0


async def get_earnings_summary(db: AsyncSession, driver_id: UUID) -> dict[str, Decimal]:
    now = _utc_now()
    today_start, today_end = today_bounds(now)
    week_start, week_end = week_bounds(now)
    month_start, month_end = month_bounds(now)

    today = await sum_earnings(db, driver_id, today_start, today_end)
    this_week = await sum_earnings(db, driver_id, week_start, week_end)
    this_month = await sum_earnings(db, driver_id, month_start, month_end)
    total = await sum_earnings(
        db,
        driver_id,
        datetime(1970, 1, 1, tzinfo=timezone.utc),
        now + timedelta(days=1),
    )
    return {
        "today": today,
        "this_week": this_week,
        "this_month": this_month,
        "total": total,
        "currency": get_settings().default_currency,
    }


def build_daily_trend(
    current_start: datetime,
    counts_by_date: dict[date, int],
    earnings_by_date: dict[date, Decimal],
) -> list[dict]:
    """Hourly buckets for the current day."""
    points: list[dict] = []
    for hour in range(24):
        label = f"{hour:02d}"
        points.append(
            {
                "label": label,
                "date": current_start.date().isoformat(),
                "ride_count": counts_by_date.get(hour, 0),
                "earnings": earnings_by_date.get(hour, Decimal("0")),
            }
        )
    return points


def build_weekly_trend(
    current_start: datetime,
    counts_by_date: dict[date, int],
    earnings_by_date: dict[date, Decimal],
) -> list[dict]:
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    points: list[dict] = []
    for i, label in enumerate(labels):
        d = current_start.date() + timedelta(days=i)
        points.append(
            {
                "label": label,
                "date": d.isoformat(),
                "ride_count": counts_by_date.get(d, 0),
                "earnings": earnings_by_date.get(d, Decimal("0")),
            }
        )
    return points


def build_monthly_trend(
    current_start: datetime,
    counts_by_date: dict[date, int],
    earnings_by_date: dict[date, Decimal],
) -> list[dict]:
    points: list[dict] = []
    start_date = current_start.date()
    if start_date.month == 12:
        end_date = date(start_date.year + 1, 1, 1)
    else:
        end_date = date(start_date.year, start_date.month + 1, 1)
    day = start_date
    while day < end_date:
        points.append(
            {
                "label": str(day.day),
                "date": day.isoformat(),
                "ride_count": counts_by_date.get(day, 0),
                "earnings": earnings_by_date.get(day, Decimal("0")),
            }
        )
        day += timedelta(days=1)
    return points
