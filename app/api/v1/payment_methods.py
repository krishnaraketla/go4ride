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
from app.services import payment_method_service

router = APIRouter(tags=["payment-methods"])


@router.get("/payment-methods", response_model=list[PaymentMethodResponse])
async def list_payment_methods(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await payment_method_service.list_payment_methods(db, rider)


@router.post("/payment-methods", response_model=PaymentMethodResponse)
async def create_payment_method(
    body: PaymentMethodCreateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await payment_method_service.create_payment_method(db, rider, body)


@router.patch("/payment-methods/{method_id}", response_model=PaymentMethodResponse)
async def update_payment_method(
    method_id: UUID,
    body: PaymentMethodUpdateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await payment_method_service.update_payment_method(db, rider, method_id, body)


@router.delete("/payment-methods/{method_id}")
async def delete_payment_method(
    method_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await payment_method_service.delete_payment_method(db, rider, method_id)
    return {"message": "Payment method deleted"}
