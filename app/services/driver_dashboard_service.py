"""Driver dashboard aggregation."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.driver import DriverProfile
from app.models.user import User
from app.schemas.driver import DriverDashboardResponse
from app.services import driver_earnings_service, driver_ride_service


async def get_dashboard(db: AsyncSession, driver: User) -> DriverDashboardResponse:
    summary = await driver_earnings_service.get_earnings_summary(db, driver.id)
    today_start, today_end = driver_earnings_service.today_bounds()
    today_trips = await driver_earnings_service.count_trips(
        db, driver.id, today_start, today_end
    )
    online_minutes = await driver_earnings_service.sum_online_minutes(
        db, driver.id, today_start, today_end
    )

    profile_result = await db.execute(
        select(DriverProfile)
        .where(DriverProfile.user_id == driver.id)
        .options(selectinload(DriverProfile.ride_type))
    )
    profile = profile_result.scalar_one_or_none()
    current_ride = await driver_ride_service.get_current_ride(db, driver)

    return DriverDashboardResponse(
        today_earnings=summary["today"],
        today_trips=today_trips,
        online_hours_today=round(online_minutes / 60, 2),
        rating=profile.rating if profile else None,
        driver_status=profile.driver_status.value if profile else "offline",
        current_ride=current_ride,
        currency=summary["currency"],
    )
