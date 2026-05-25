from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PaymentMethodCreateRequest(BaseModel):
    brand: str = Field(..., min_length=1, max_length=32)
    last4: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    exp_month: int = Field(..., ge=1, le=12)
    exp_year: int = Field(..., ge=2024, le=2099)
    is_default: bool = False


class PaymentMethodUpdateRequest(BaseModel):
    is_default: bool | None = None


class PaymentMethodResponse(BaseModel):
    id: UUID
    brand: str
    last4: str
    exp_month: int
    exp_year: int
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}
