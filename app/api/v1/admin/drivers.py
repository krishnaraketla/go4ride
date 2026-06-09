"""Admin endpoints for driver KYC application review."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import verify_admin_key
from app.db.session import get_db
from app.models.enums import OnboardingStatus
from app.schemas.admin import (
    DriverApplicationActionResponse,
    DriverApplicationDetailResponse,
    DriverApplicationListResponse,
    RejectDriverApplicationRequest,
)
from app.schemas.response import ApiResponse, ok
from app.services import admin_driver_service

router = APIRouter(prefix="/driver-applications", tags=["Admin — Driver KYC"])


@router.get("", response_model=ApiResponse[DriverApplicationListResponse])
async def list_driver_applications(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(verify_admin_key)],
    status: OnboardingStatus = Query(default=OnboardingStatus.under_review),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    data = await admin_driver_service.list_driver_applications(
        db, status=status, page=page, limit=limit
    )
    return ok(data, message="Driver applications retrieved")


@router.get("/{driver_id}", response_model=ApiResponse[DriverApplicationDetailResponse])
async def get_driver_application(
    driver_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(verify_admin_key)],
):
    data = await admin_driver_service.get_driver_application(db, driver_id)
    return ok(data, message="Driver application retrieved")


@router.post("/{driver_id}/approve", response_model=ApiResponse[DriverApplicationActionResponse])
async def approve_driver_application(
    driver_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(verify_admin_key)],
):
    data = await admin_driver_service.approve_driver_application(db, driver_id)
    return ok(data, message="Driver application approved")


@router.post("/{driver_id}/reject", response_model=ApiResponse[DriverApplicationActionResponse])
async def reject_driver_application(
    driver_id: UUID,
    body: RejectDriverApplicationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(verify_admin_key)],
):
    data = await admin_driver_service.reject_driver_application(db, driver_id, body.reason)
    return ok(data, message="Driver application rejected")
