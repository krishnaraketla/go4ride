"""Bidirectional ride ratings."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import bad_request, conflict, forbidden, not_found
from app.models.driver import DriverProfile
from app.models.enums import RaterRole, RideStatus, UserRole
from app.models.ride import Ride
from app.models.ride_rating import RideRating
from app.models.user import User


async def submit_rating(
    db: AsyncSession,
    ride: Ride,
    rater: User,
    score: int,
    comment: str | None = None,
) -> RideRating:
    if ride.status != RideStatus.completed:
        raise bad_request("Can only rate completed rides", "RIDE_NOT_COMPLETED")
    if score < 1 or score > 5:
        raise bad_request("Score must be between 1 and 5", "INVALID_SCORE")

    if rater.role == UserRole.rider:
        if ride.rider_id != rater.id:
            raise forbidden("Not your ride")
        if ride.driver_id is None:
            raise bad_request("Ride has no driver", "NO_DRIVER")
        rater_role = RaterRole.rider
        ratee_id = ride.driver_id
    elif rater.role == UserRole.driver:
        if ride.driver_id != rater.id:
            raise forbidden("Not your ride")
        rater_role = RaterRole.driver
        ratee_id = ride.rider_id
    else:
        raise forbidden("Invalid role for rating")

    existing = await db.execute(
        select(RideRating).where(
            RideRating.ride_id == ride.id,
            RideRating.rater_role == rater_role,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise conflict("Rating already submitted for this ride", "RATING_EXISTS")

    rating = RideRating(
        ride_id=ride.id,
        rater_id=rater.id,
        ratee_id=ratee_id,
        rater_role=rater_role,
        score=score,
        comment=comment,
    )
    db.add(rating)
    await db.flush()

    if rater_role == RaterRole.rider and ride.driver_id is not None:
        await update_driver_aggregate_rating(db, ride.driver_id)

    return rating


async def get_rider_rating_for_ride(db: AsyncSession, ride_id: UUID) -> int | None:
    """Rating the rider gave to the driver (shown on driver trip history)."""
    result = await db.execute(
        select(RideRating.score).where(
            RideRating.ride_id == ride_id,
            RideRating.rater_role == RaterRole.rider,
        )
    )
    score = result.scalar_one_or_none()
    return score


async def get_ratings_for_rides(
    db: AsyncSession, ride_ids: list[UUID]
) -> dict[UUID, int]:
    if not ride_ids:
        return {}
    result = await db.execute(
        select(RideRating.ride_id, RideRating.score).where(
            RideRating.ride_id.in_(ride_ids),
            RideRating.rater_role == RaterRole.rider,
        )
    )
    return {ride_id: score for ride_id, score in result.all()}


async def update_driver_aggregate_rating(db: AsyncSession, driver_id: UUID) -> None:
    avg_result = await db.execute(
        select(func.avg(RideRating.score))
        .join(Ride, Ride.id == RideRating.ride_id)
        .where(
            Ride.driver_id == driver_id,
            RideRating.rater_role == RaterRole.rider,
        )
    )
    avg_score = avg_result.scalar()
    if avg_score is None:
        return

    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise not_found("Driver profile not found", "PROFILE_NOT_FOUND")
    profile.rating = Decimal(str(round(float(avg_score), 2)))
    await db.flush()


async def get_ride_for_rating(
    db: AsyncSession, ride_id: UUID, rater: User
) -> Ride:
    result = await db.execute(select(Ride).where(Ride.id == ride_id))
    ride = result.scalar_one_or_none()
    if ride is None:
        raise not_found("Ride not found", "RIDE_NOT_FOUND")
    return ride
