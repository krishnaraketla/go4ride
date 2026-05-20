from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileResponse(BaseModel):
    id: UUID
    phone: str
    email: str | None
    name: str | None
    avatar_url: str | None
    role: str


class ProfileUpdateRequest(BaseModel):
    name: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    avatar_url: str | None = Field(None, max_length=512)


class StatsResponse(BaseModel):
    total_rides: int
    completed_rides: int
    total_spend: Decimal
    currency: str = "INR"
