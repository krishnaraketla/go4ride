from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.payment import (
    PaymentMethodCreateRequest,
    PaymentMethodResponse,
    PaymentMethodUpdateRequest,
)
from app.schemas.response import ApiResponse, ok
from app.services import payment_method_service

router = APIRouter(tags=["payment-methods"])


@router.get("/payment-methods", response_model=ApiResponse[list[PaymentMethodResponse]])
async def list_payment_methods(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List saved payment methods (stub metadata only)."""

    methods = await payment_method_service.list_payment_methods(db, rider)
    return ok(methods, message="Payment methods retrieved")


@router.post("/payment-methods", response_model=ApiResponse[PaymentMethodResponse])
async def create_payment_method(
    body: PaymentMethodCreateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Add card metadata (last4, brand — no PAN storage)."""

    method = await payment_method_service.create_payment_method(db, rider, body)
    return ok(method, message="Payment method added")


@router.patch("/payment-methods/{method_id}", response_model=ApiResponse[PaymentMethodResponse])
async def update_payment_method(
    method_id: UUID,
    body: PaymentMethodUpdateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Set the default payment method."""

    method = await payment_method_service.update_payment_method(db, rider, method_id, body)
    return ok(method, message="Payment method updated")


@router.delete("/payment-methods/{method_id}", response_model=ApiResponse[None])
async def delete_payment_method(
    method_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Remove a saved payment method."""

    await payment_method_service.delete_payment_method(db, rider, method_id)
    return ok(message="Payment method deleted")
