from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.db.session import get_db
from app.models.user import User
from app.schemas.driver import DriverDashboardResponse
from app.schemas.response import ApiResponse, ok
from app.services import driver_dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Driver Dashboard"])


@router.get("", response_model=ApiResponse[DriverDashboardResponse])
async def get_dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    data = await driver_dashboard_service.get_dashboard(db, driver)
    return ok(data, message="Dashboard retrieved")
