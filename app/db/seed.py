"""Seed ride types, fare rules, and mock driver for Phase 1 / 1.5."""
import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.driver import DriverProfile
from app.models.enums import UserRole
from app.models.ride import FareRule, RideType
from app.models.user import User

MOCK_DRIVER_PHONE = "+919999000001"
MOCK_DRIVER_NAME = "Dev Driver"
MOCK_DRIVER_VEHICLE = {
    "vehicle_model": "Toyota Etios",
    "vehicle_plate": "KA01AB1234",
    "vehicle_color": "white",
    "current_lat": Decimal("12.9700"),
    "current_lng": Decimal("77.5900"),
}


async def seed() -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(RideType))
        if not result.scalars().first():
            mini = RideType(
                slug="mini",
                name="Go4 Mini",
                description="Affordable compact rides",
                icon_url=None,
            )
            sedan = RideType(
                slug="sedan",
                name="Go4 Sedan",
                description="Comfortable sedan rides",
                icon_url=None,
            )
            db.add_all([mini, sedan])
            await db.flush()

            db.add_all(
                [
                    FareRule(
                        ride_type_id=mini.id,
                        base_fare=Decimal("40"),
                        per_km_rate=Decimal("12"),
                        per_min_rate=Decimal("2"),
                        minimum_fare=Decimal("60"),
                    ),
                    FareRule(
                        ride_type_id=sedan.id,
                        base_fare=Decimal("60"),
                        per_km_rate=Decimal("16"),
                        per_min_rate=Decimal("2.5"),
                        minimum_fare=Decimal("80"),
                    ),
                ]
            )
            print("Seeded ride types (mini, sedan) and fare rules")
        else:
            print("Ride types already seeded")

        driver_result = await db.execute(select(User).where(User.phone == MOCK_DRIVER_PHONE))
        driver_user = driver_result.scalar_one_or_none()
        if driver_user is None:
            driver_user = User(
                phone=MOCK_DRIVER_PHONE,
                name=MOCK_DRIVER_NAME,
                role=UserRole.driver,
            )
            db.add(driver_user)
            await db.flush()
            db.add(DriverProfile(user_id=driver_user.id, **MOCK_DRIVER_VEHICLE))
            print(f"Seeded mock driver ({MOCK_DRIVER_PHONE})")
        else:
            profile_result = await db.execute(
                select(DriverProfile).where(DriverProfile.user_id == driver_user.id)
            )
            if profile_result.scalar_one_or_none() is None:
                db.add(DriverProfile(user_id=driver_user.id, **MOCK_DRIVER_VEHICLE))
                print(f"Seeded driver profile for existing user ({MOCK_DRIVER_PHONE})")
            else:
                print(f"Mock driver already seeded ({MOCK_DRIVER_PHONE})")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
