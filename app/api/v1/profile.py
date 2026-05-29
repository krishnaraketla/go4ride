from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest, StatsResponse
from app.schemas.response import ApiResponse, ok
from app.services import profile_service

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ApiResponse[ProfileResponse])
async def get_profile(rider: Annotated[User, Depends(get_current_rider)]):
    """Get the current rider's profile."""

    return ok(
        ProfileResponse(
            id=rider.id,
            phone=rider.phone,
            email=rider.email,
            name=rider.name,
            avatar_url=rider.avatar_url,
            role=rider.role.value,
        ),
        message="Profile retrieved",
    )


@router.patch("/profile", response_model=ApiResponse[ProfileResponse])
async def update_profile(
    body: ProfileUpdateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update name, email, or avatar. Changing email resets verification."""

    user = await profile_service.update_profile(db, rider, body)
    return ok(
        ProfileResponse(
            id=user.id,
            phone=user.phone,
            email=user.email,
            name=user.name,
            avatar_url=user.avatar_url,
            role=user.role.value,
        ),
        message="Profile updated",
    )


@router.get("/stats", response_model=ApiResponse[StatsResponse])
async def stats(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Lifetime ride count, distance, and spend for the rider."""

    data = await profile_service.get_rider_stats(db, rider.id)
    return ok(data, message="Stats retrieved")
