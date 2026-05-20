from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest, StatsResponse
from app.services import profile_service

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(rider: Annotated[User, Depends(get_current_rider)]):
    return ProfileResponse(
        id=rider.id,
        phone=rider.phone,
        email=rider.email,
        name=rider.name,
        avatar_url=rider.avatar_url,
        role=rider.role.value,
    )


@router.patch("/profile", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await profile_service.update_profile(db, rider, body)
    return ProfileResponse(
        id=user.id,
        phone=user.phone,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        role=user.role.value,
    )


@router.get("/stats", response_model=StatsResponse)
async def stats(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await profile_service.get_rider_stats(db, rider.id)
