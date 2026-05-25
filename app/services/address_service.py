from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import bad_request, not_found
from app.models.address import SavedAddress
from app.models.user import User
from app.schemas.address import AddressCreateRequest, AddressResponse, AddressUpdateRequest
from app.services.geo_service import haversine_distance_m


async def list_addresses(
    db: AsyncSession,
    user: User,
    lat: Decimal | None = None,
    lng: Decimal | None = None,
) -> list[AddressResponse]:
    result = await db.execute(
        select(SavedAddress).where(SavedAddress.user_id == user.id).order_by(SavedAddress.created_at.desc())
    )
    addresses = result.scalars().all()
    items = []
    for addr in addresses:
        distance_m = None
        if lat is not None and lng is not None:
            distance_m = haversine_distance_m(lat, lng, addr.lat, addr.lng)
        items.append(_to_response(addr, distance_m))
    if lat is not None and lng is not None:
        items.sort(key=lambda a: a.distance_m if a.distance_m is not None else 10**9)
    return items


async def create_address(
    db: AsyncSession, user: User, data: AddressCreateRequest
) -> AddressResponse:
    settings = get_settings()
    count = (
        await db.execute(
            select(func.count()).select_from(SavedAddress).where(SavedAddress.user_id == user.id)
        )
    ).scalar() or 0
    if count >= settings.max_saved_addresses_per_user:
        raise bad_request("Maximum saved addresses reached", "ADDRESS_LIMIT_REACHED")

    if data.is_default:
        await _clear_defaults(db, user.id)

    addr = SavedAddress(
        user_id=user.id,
        label=data.label,
        address_line=data.address_line,
        lat=data.lat,
        lng=data.lng,
        is_default=data.is_default,
    )
    db.add(addr)
    await db.flush()
    return _to_response(addr, None)


async def update_address(
    db: AsyncSession, user: User, address_id: UUID, data: AddressUpdateRequest
) -> AddressResponse:
    addr = await _get_address(db, user.id, address_id)
    if data.label is not None:
        addr.label = data.label
    if data.address_line is not None:
        addr.address_line = data.address_line
    if data.lat is not None:
        addr.lat = data.lat
    if data.lng is not None:
        addr.lng = data.lng
    if data.is_default is True:
        await _clear_defaults(db, user.id)
        addr.is_default = True
    elif data.is_default is False:
        addr.is_default = False
    return _to_response(addr, None)


async def delete_address(db: AsyncSession, user: User, address_id: UUID) -> None:
    addr = await _get_address(db, user.id, address_id)
    await db.delete(addr)


async def _get_address(db: AsyncSession, user_id: UUID, address_id: UUID) -> SavedAddress:
    result = await db.execute(
        select(SavedAddress).where(SavedAddress.id == address_id, SavedAddress.user_id == user_id)
    )
    addr = result.scalar_one_or_none()
    if addr is None:
        raise not_found("Address not found", "ADDRESS_NOT_FOUND")
    return addr


async def _clear_defaults(db: AsyncSession, user_id: UUID) -> None:
    result = await db.execute(select(SavedAddress).where(SavedAddress.user_id == user_id))
    for addr in result.scalars().all():
        addr.is_default = False


def _to_response(addr: SavedAddress, distance_m: int | None) -> AddressResponse:
    return AddressResponse(
        id=addr.id,
        label=addr.label,
        address_line=addr.address_line,
        lat=addr.lat,
        lng=addr.lng,
        is_default=addr.is_default,
        distance_m=distance_m,
        created_at=addr.created_at,
        updated_at=addr.updated_at,
    )
