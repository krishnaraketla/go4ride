"""Driver performance stats."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver import DriverProfile
from app.models.driver_ride_action import DriverRideAction
from app.models.enums import DriverRideActionType, RideStatus
from app.models.ride import Ride
from app.services import driver_earnings_service as earnings_svc


async def get_driver_stats(
    db: AsyncSession,
    driver_id: UUID,
    *,
    period: str = "all",
) -> dict:
    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver_id)
    )
    profile = profile_result.scalar_one_or_none()

    start, end = _period_range(period)

    completed = await _count_rides(db, driver_id, RideStatus.completed, start, end)
    cancelled = await _count_cancelled_assigned(db, driver_id, start, end)
    total = completed + cancelled

    acceptance_rate = await _acceptance_rate(db, driver_id, start, end)
    completion_rate = round(completed / total, 4) if total > 0 else 1.0

    active_minutes = await earnings_svc.sum_active_minutes(db, driver_id, start, end)
    online_minutes = await earnings_svc.sum_online_minutes(db, driver_id, start, end)

    return {
        "total_rides": completed,
        "completed_rides": completed,
        "cancelled_rides": cancelled,
        "acceptance_rate": acceptance_rate,
        "completion_rate": completion_rate,
        "rating": profile.rating if profile else None,
        "active_hours": round(active_minutes / 60, 2),
        "online_hours": round(online_minutes / 60, 2),
    }


def _period_range(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if period == "weekly":
        return earnings_svc.week_bounds(now)
    if period == "monthly":
        return earnings_svc.month_bounds(now)
    if period == "daily":
        return earnings_svc.today_bounds(now)
    return datetime(1970, 1, 1, tzinfo=timezone.utc), now + timedelta(days=1)


async def _count_rides(
    db: AsyncSession,
    driver_id: UUID,
    status: RideStatus,
    start: datetime,
    end: datetime,
) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Ride)
        .where(
            Ride.driver_id == driver_id,
            Ride.status == status,
            Ride.completed_at >= start,
            Ride.completed_at < end,
        )
    )
    return result.scalar() or 0


async def _count_cancelled_assigned(
    db: AsyncSession,
    driver_id: UUID,
    start: datetime,
    end: datetime,
) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Ride)
        .where(
            Ride.driver_id == driver_id,
            Ride.status == RideStatus.cancelled,
            Ride.cancelled_at >= start,
            Ride.cancelled_at < end,
        )
    )
    return result.scalar() or 0


async def _acceptance_rate(
    db: AsyncSession,
    driver_id: UUID,
    start: datetime,
    end: datetime,
) -> float:
    accepted = await _action_count(db, driver_id, DriverRideActionType.accepted, start, end)
    rejected = await _action_count(db, driver_id, DriverRideActionType.rejected, start, end)
    total = accepted + rejected
    if total == 0:
        return 1.0
    return round(accepted / total, 4)


async def _action_count(
    db: AsyncSession,
    driver_id: UUID,
    action: DriverRideActionType,
    start: datetime,
    end: datetime,
) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(DriverRideAction)
        .where(
            DriverRideAction.driver_id == driver_id,
            DriverRideAction.action == action,
            DriverRideAction.created_at >= start,
            DriverRideAction.created_at < end,
        )
    )
    return result.scalar() or 0
