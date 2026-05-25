from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.address import AddressCreateRequest, AddressResponse, AddressUpdateRequest
from app.services import address_service

router = APIRouter(tags=["addresses"])


@router.get("/addresses", response_model=list[AddressResponse])
async def list_addresses(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
    lat: Decimal | None = Query(None),
    lng: Decimal | None = Query(None),
):
    return await address_service.list_addresses(db, rider, lat, lng)


@router.post("/addresses", response_model=AddressResponse)
async def create_address(
    body: AddressCreateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await address_service.create_address(db, rider, body)


@router.patch("/addresses/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: UUID,
    body: AddressUpdateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await address_service.update_address(db, rider, address_id, body)


@router.delete("/addresses/{address_id}")
async def delete_address(
    address_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await address_service.delete_address(db, rider, address_id)
    return {"message": "Address deleted"}
