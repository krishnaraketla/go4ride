"""Clear all ride data on startup when CLEAR_RIDES_ON_STARTUP is enabled."""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, update

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.driver import DriverProfile
from app.models.enums import DriverStatus
from app.models.ride import Ride, RideStatusEvent


async def clear_rides() -> tuple[int, int, int]:
    """Delete all rides and status events; reset drivers stuck on_ride."""
    async with async_session_factory() as db:
        events_result = await db.execute(delete(RideStatusEvent))
        rides_result = await db.execute(delete(Ride))
        drivers_result = await db.execute(
            update(DriverProfile)
            .where(DriverProfile.driver_status == DriverStatus.on_ride)
            .values(driver_status=DriverStatus.offline)
        )
        await db.commit()
        return (
            events_result.rowcount or 0,
            rides_result.rowcount or 0,
            drivers_result.rowcount or 0,
        )


async def clear_rides_on_startup_if_enabled() -> None:
    settings = get_settings()
    if not settings.clear_rides_on_startup:
        print("CLEAR_RIDES_ON_STARTUP disabled; skipping ride cleanup")
        return
    events, rides, drivers = await clear_rides()
    print(
        f"Cleared {rides} ride(s), {events} status event(s); "
        f"reset {drivers} driver(s) from on_ride to offline"
    )


def main() -> None:
    asyncio.run(clear_rides_on_startup_if_enabled())


if __name__ == "__main__":
    main()
