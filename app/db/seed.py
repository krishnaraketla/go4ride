"""Seed ride types, fare rules, and mock driver for Phase 1 / 1.5."""
import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.driver import DriverProfile
from app.models.enums import KycStatus, OnboardingStatus, UserRole
from app.models.ride import FareRule, RideType
from app.models.user import User
from app.models.wallet import PaymentMethod, PromoCode

MOCK_DRIVER_PHONE = "+919999000001"
MOCK_DRIVER_NAME = "Dev Driver"
MOCK_DRIVER_VEHICLE = {
    "vehicle_model": "Toyota Etios",
    "vehicle_plate": "KA01AB1234",
    "vehicle_color": "white",
    "current_lat": Decimal("12.9700"),
    "current_lng": Decimal("77.5900"),
    "kyc_status": KycStatus.approved,
    "onboarding_status": OnboardingStatus.approved,
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
            bike = RideType(
                slug="bike",
                name="Go4 Bike",
                description="Quick bike rides",
                icon_url=None,
            )
            xl = RideType(
                slug="xl",
                name="Go4 XL",
                description="Spacious XL rides",
                icon_url=None,
            )
            db.add_all([mini, sedan, bike, xl])
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
                    FareRule(
                        ride_type_id=bike.id,
                        base_fare=Decimal("25"),
                        per_km_rate=Decimal("8"),
                        per_min_rate=Decimal("1.5"),
                        minimum_fare=Decimal("40"),
                    ),
                    FareRule(
                        ride_type_id=xl.id,
                        base_fare=Decimal("80"),
                        per_km_rate=Decimal("20"),
                        per_min_rate=Decimal("3"),
                        minimum_fare=Decimal("100"),
                    ),
                ]
            )
            print("Seeded ride types (mini, sedan, bike, xl) and fare rules")
        else:
            for slug, name, desc, base, per_km, per_min, minimum in [
                ("bike", "Go4 Bike", "Quick bike rides", "25", "8", "1.5", "40"),
                ("xl", "Go4 XL", "Spacious XL rides", "80", "20", "3", "100"),
            ]:
                existing = await db.execute(select(RideType).where(RideType.slug == slug))
                if existing.scalar_one_or_none() is None:
                    rt = RideType(slug=slug, name=name, description=desc, icon_url=None)
                    db.add(rt)
                    await db.flush()
                    db.add(
                        FareRule(
                            ride_type_id=rt.id,
                            base_fare=Decimal(base),
                            per_km_rate=Decimal(per_km),
                            per_min_rate=Decimal(per_min),
                            minimum_fare=Decimal(minimum),
                        )
                    )
                    print(f"Seeded ride type {slug}")

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
            profile = profile_result.scalar_one_or_none()
            if profile is None:
                db.add(DriverProfile(user_id=driver_user.id, **MOCK_DRIVER_VEHICLE))
                print(f"Seeded driver profile for existing user ({MOCK_DRIVER_PHONE})")
            else:
                profile.kyc_status = KycStatus.approved
                profile.onboarding_status = OnboardingStatus.approved
                print(f"Mock driver already seeded ({MOCK_DRIVER_PHONE}); KYC ensured approved")

        promo_result = await db.execute(select(PromoCode).where(PromoCode.code == "WELCOME5"))
        if promo_result.scalar_one_or_none() is None:
            db.add(
                PromoCode(
                    code="WELCOME5",
                    amount=Decimal("5.00"),
                    max_uses=None,
                    is_active=True,
                )
            )
            print("Seeded promo code WELCOME5")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
