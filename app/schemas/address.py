from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AddressCreateRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=64)
    address_line: str = Field(..., min_length=1)
    lat: Decimal = Field(..., ge=-90, le=90)
    lng: Decimal = Field(..., ge=-180, le=180)
    is_default: bool = False


class AddressUpdateRequest(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=64)
    address_line: str | None = None
    lat: Decimal | None = Field(None, ge=-90, le=90)
    lng: Decimal | None = Field(None, ge=-180, le=180)
    is_default: bool | None = None


class AddressResponse(BaseModel):
    id: UUID
    label: str
    address_line: str
    lat: Decimal
    lng: Decimal
    is_default: bool
    distance_m: int | None = None
    created_at: datetime
    updated_at: datetime
