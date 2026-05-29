from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.address import AddressCreateRequest, AddressResponse, AddressUpdateRequest
from app.schemas.response import ApiResponse, ok
from app.services import address_service

router = APIRouter(tags=["addresses"])


@router.get("/addresses", response_model=ApiResponse[list[AddressResponse]])
async def list_addresses(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
    lat: Decimal | None = Query(None),
    lng: Decimal | None = Query(None),
):
    """List saved addresses; pass `lat`/`lng` to sort by distance."""

    addresses = await address_service.list_addresses(db, rider, lat, lng)
    return ok(addresses, message="Addresses retrieved")


@router.post("/addresses", response_model=ApiResponse[AddressResponse])
async def create_address(
    body: AddressCreateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a saved address (max 10 per user)."""

    address = await address_service.create_address(db, rider, body)
    return ok(address, message="Address created")


@router.patch("/addresses/{address_id}", response_model=ApiResponse[AddressResponse])
async def update_address(
    address_id: UUID,
    body: AddressUpdateRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update label, coordinates, or default flag on a saved address."""

    address = await address_service.update_address(db, rider, address_id, body)
    return ok(address, message="Address updated")


@router.delete("/addresses/{address_id}", response_model=ApiResponse[None])
async def delete_address(
    address_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a saved address."""

    await address_service.delete_address(db, rider, address_id)
    return ok(message="Address deleted")
