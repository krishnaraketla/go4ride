import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.seed import MOCK_DRIVER_PHONE
from app.db.session import async_session_factory
from app.models.driver import DriverProfile
from app.models.enums import RideStatus
from app.models.ride import Ride
from app.models.user import User
from app.services import ride_service

logger = logging.getLogger(__name__)

_mock_driver_id: UUID | None = None
_scheduled_rides: set[UUID] = set()


def schedule_mock_lifecycle(ride_id: UUID) -> None:
    settings = get_settings()
    if not settings.mock_driver_enabled:
        return
    if ride_id in _scheduled_rides:
        return
    _scheduled_rides.add(ride_id)
    asyncio.create_task(_run_mock_lifecycle(ride_id))


async def _run_mock_lifecycle(ride_id: UUID) -> None:
    settings = get_settings()
    try:
        await asyncio.sleep(settings.mock_driver_assign_delay_sec)
        await _assign_driver(ride_id)

        if not settings.mock_driver_auto_advance:
            return

        step_delay = settings.mock_driver_step_delay_sec
        for status, message in (
            (RideStatus.driver_arrived, "Driver has arrived"),
            (RideStatus.in_progress, "Trip started"),
            (RideStatus.completed, "Trip completed"),
        ):
            await asyncio.sleep(step_delay)
            if not await _advance_if_active(ride_id, status, message):
                return
    except Exception:
        logger.exception("Mock driver lifecycle failed for ride %s", ride_id)
    finally:
        _scheduled_rides.discard(ride_id)


async def _get_mock_driver_id() -> UUID:
    global _mock_driver_id
    if _mock_driver_id is not None:
        return _mock_driver_id
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.phone == MOCK_DRIVER_PHONE))
        user = result.scalar_one()
        _mock_driver_id = user.id
        return user.id


async def _assign_driver(ride_id: UUID) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Ride).where(Ride.id == ride_id))
        ride = result.scalar_one_or_none()
        if ride is None or ride.status in ride_service.TERMINAL_STATUSES:
            return
        if ride.status != RideStatus.searching_driver:
            return

        driver_id = await _get_mock_driver_id()
        profile_result = await db.execute(
            select(DriverProfile).where(DriverProfile.user_id == driver_id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile is not None and ride.pickup_lat is not None:
            profile.current_lat = ride.pickup_lat
            profile.current_lng = ride.pickup_lng

        await ride_service.transition_ride(
            db,
            ride_id,
            RideStatus.driver_assigned,
            driver_id=driver_id,
            message="Driver assigned",
        )
        await db.commit()


async def _advance_if_active(ride_id: UUID, status: RideStatus, message: str) -> bool:
    async with async_session_factory() as db:
        result = await db.execute(select(Ride).where(Ride.id == ride_id))
        ride = result.scalar_one_or_none()
        if ride is None or ride.status in ride_service.TERMINAL_STATUSES:
            return False
        await ride_service.transition_ride(db, ride_id, status, message=message)
        await db.commit()
        return True
