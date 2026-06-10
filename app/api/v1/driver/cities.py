"""Driver city selection for onboarding."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.db.session import get_db
from app.models.city import City
from app.models.user import User
from app.schemas.driver import CityResponse
from app.schemas.response import ApiResponse, ok

router = APIRouter(prefix="/cities", tags=["Driver Cities"])


@router.get("", response_model=ApiResponse[list[CityResponse]])
async def list_cities(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_driver)],
):
    result = await db.execute(
        select(City).where(City.is_active.is_(True)).order_by(City.name)
    )
    cities = result.scalars().all()
    return ok(
        [
            CityResponse(id=city.id, slug=city.slug, name=city.name, state=city.state)
            for city in cities
        ],
        message="Cities retrieved",
    )
