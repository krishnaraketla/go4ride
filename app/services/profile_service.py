from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RideStatus
from app.models.ride import Ride
from app.models.user import User
from app.schemas.profile import ProfileUpdateRequest, StatsResponse


async def get_profile(user: User) -> User:
    return user


async def update_profile(db: AsyncSession, user: User, data: ProfileUpdateRequest) -> User:
    if data.name is not None:
        user.name = data.name
    if data.email is not None:
        user.email = data.email
    if data.avatar_url is not None:
        user.avatar_url = data.avatar_url
    return user


async def get_rider_stats(db: AsyncSession, rider_id: UUID) -> StatsResponse:
    total = (
        await db.execute(select(func.count()).select_from(Ride).where(Ride.rider_id == rider_id))
    ).scalar() or 0
    completed = (
        await db.execute(
            select(func.count()).select_from(Ride).where(
                Ride.rider_id == rider_id, Ride.status == RideStatus.completed
            )
        )
    ).scalar() or 0
    spend = (
        await db.execute(
            select(func.coalesce(func.sum(Ride.final_fare), 0)).where(
                Ride.rider_id == rider_id, Ride.status == RideStatus.completed
            )
        )
    ).scalar() or Decimal("0")
    return StatsResponse(total_rides=total, completed_rides=completed, total_spend=spend)
