"""Seed ride types, fare rules, cities, mock driver, and env-configured test users."""
import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.city import City
from app.models.driver import DriverProfile
from app.models.enums import KycStatus, OnboardingStatus, UserRole
from app.models.ride import FareRule, RideType
from app.models.user import User
from app.models.wallet import PromoCode

MOCK_DRIVER_PHONE = "+15555550001"
MOCK_DRIVER_NAME = "Dev Driver"

CITIES = [
    ("san-francisco", "San Francisco", "California"),
    ("new-york", "New York", "New York"),
    ("los-angeles", "Los Angeles", "California"),
    ("chicago", "Chicago", "Illinois"),
    ("austin", "Austin", "Texas"),
    ("seattle", "Seattle", "Washington"),
    ("miami", "Miami", "Florida"),
    ("dallas", "Dallas", "Texas"),
]


def _approved_driver_profile_fields(city_id: uuid.UUID | None) -> dict:
    return {
        "vehicle_model": "Toyota Camry",
        "vehicle_plate": "CA7AB1234",
        "vehicle_color": "white",
        "current_lat": Decimal("37.7749"),
        "current_lng": Decimal("-122.4194"),
        "kyc_status": KycStatus.approved,
        "onboarding_status": OnboardingStatus.kyc_approved,
        "city_id": city_id,
    }


async def _ensure_rider(db: AsyncSession, phone: str, name: str) -> None:
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()
    if user is None:
        db.add(User(phone=phone, name=name, role=UserRole.rider))
        print(f"Seeded test rider ({phone})")
        return
    if user.role != UserRole.rider:
        print(f"Skipping seed for {phone}: already exists as {user.role.value}")
        return
    if name and not user.name:
        user.name = name
    print(f"Test rider already seeded ({phone})")


async def _ensure_driver(
    db: AsyncSession,
    phone: str,
    name: str,
    city_id: uuid.UUID | None,
    *,
    label: str = "driver",
) -> None:
    profile_fields = _approved_driver_profile_fields(city_id)
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(phone=phone, name=name, role=UserRole.driver)
        db.add(user)
        await db.flush()
        db.add(DriverProfile(user_id=user.id, **profile_fields))
        print(f"Seeded {label} ({phone})")
        return
    if user.role != UserRole.driver:
        print(f"Skipping seed for {phone}: already exists as {user.role.value}")
        return
    if name and not user.name:
        user.name = name
    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        db.add(DriverProfile(user_id=user.id, **profile_fields))
        print(f"Seeded driver profile for existing user ({phone})")
        return
    profile.kyc_status = KycStatus.approved
    profile.onboarding_status = OnboardingStatus.kyc_approved
    if city_id and profile.city_id is None:
        profile.city_id = city_id
    print(f"{label.capitalize()} already seeded ({phone}); KYC ensured approved")


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
                        base_fare=Decimal("2.50"),
                        per_km_rate=Decimal("1.20"),
                        per_min_rate=Decimal("0.25"),
                        minimum_fare=Decimal("5.00"),
                        currency="USD",
                    ),
                    FareRule(
                        ride_type_id=sedan.id,
                        base_fare=Decimal("3.50"),
                        per_km_rate=Decimal("1.50"),
                        per_min_rate=Decimal("0.30"),
                        minimum_fare=Decimal("7.00"),
                        currency="USD",
                    ),
                    FareRule(
                        ride_type_id=bike.id,
                        base_fare=Decimal("2.00"),
                        per_km_rate=Decimal("0.90"),
                        per_min_rate=Decimal("0.20"),
                        minimum_fare=Decimal("4.00"),
                        currency="USD",
                    ),
                    FareRule(
                        ride_type_id=xl.id,
                        base_fare=Decimal("4.00"),
                        per_km_rate=Decimal("1.80"),
                        per_min_rate=Decimal("0.35"),
                        minimum_fare=Decimal("8.00"),
                        currency="USD",
                    ),
                ]
            )
            print("Seeded ride types (mini, sedan, bike, xl) and fare rules")
        else:
            for slug, name, desc, base, per_km, per_min, minimum in [
                ("bike", "Go4 Bike", "Quick bike rides", "2.00", "0.90", "0.20", "4.00"),
                ("xl", "Go4 XL", "Spacious XL rides", "4.00", "1.80", "0.35", "8.00"),
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
                            currency="USD",
                        )
                    )
                    print(f"Seeded ride type {slug}")

        for slug, name, state in CITIES:
            existing = await db.execute(select(City).where(City.slug == slug))
            if existing.scalar_one_or_none() is None:
                db.add(City(slug=slug, name=name, state=state, is_active=True))
                print(f"Seeded city {slug}")

        sf_result = await db.execute(select(City).where(City.slug == "san-francisco"))
        san_francisco = sf_result.scalar_one_or_none()
        city_id = san_francisco.id if san_francisco else None

        await _ensure_driver(
            db, MOCK_DRIVER_PHONE, MOCK_DRIVER_NAME, city_id, label="mock driver"
        )

        settings = get_settings()
        for entry in settings.seed_test_users:
            phone = entry.get("phone", "").strip()
            name = entry.get("name", "").strip() or "Test User"
            role = entry.get("role", "rider").strip().lower()
            if not phone:
                continue
            if role == "driver":
                await _ensure_driver(db, phone, name, city_id, label="test driver")
            elif role == "rider":
                await _ensure_rider(db, phone, name)
            else:
                print(f"Skipping seed for {phone}: unknown role {role!r}")

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
