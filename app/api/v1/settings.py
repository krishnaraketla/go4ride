from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.settings import SettingsResponse, SettingsUpdateRequest
from app.services import settings_service

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get notification and app preferences."""

    return await settings_service.get_settings(db, rider)


@router.patch("/settings", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update notification and app preferences."""

    return await settings_service.update_settings(db, rider, body)
