"""Seed ride types and fare rules for Phase 1."""
import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.ride import FareRule, RideType


async def seed() -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(RideType))
        if result.scalars().first():
            print("Seed already applied")
            return

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
        await db.commit()
        print("Seeded ride types (mini, sedan) and fare rules")


if __name__ == "__main__":
    asyncio.run(seed())
