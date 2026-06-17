from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.db.session import get_db
from app.models.user import User
from app.schemas.driver_insights import DriverInsightsResponse
from app.schemas.response import ApiResponse, ok
from app.services import driver_insights_service

router = APIRouter(prefix="/insights", tags=["Driver Insights"])


@router.get("", response_model=ApiResponse[DriverInsightsResponse])
async def driver_insights(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
    period: Literal["daily", "weekly", "monthly"] = Query("weekly"),
):
    data = await driver_insights_service.get_driver_insights(db, driver.id, period)
    return ok(data, message="Insights retrieved")
