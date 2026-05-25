from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.insights import InsightsResponse
from app.services import insights_service

router = APIRouter(tags=["insights"])


@router.get("/insights", response_model=InsightsResponse)
async def insights(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Literal["weekly", "monthly"] = Query("weekly"),
):
    return await insights_service.get_insights(db, rider.id, period)
