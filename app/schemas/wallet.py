from decimal import Decimal

from pydantic import BaseModel, Field


class WalletResponse(BaseModel):
    balance: Decimal
    currency: str


class PromoApplyRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)


class PromoApplyResponse(BaseModel):
    balance: Decimal
    currency: str
    credited: Decimal
    message: str


class ReferralResponse(BaseModel):
    code: str
    reward_amount: Decimal
    currency: str


class PartnerInterestRequest(BaseModel):
    message: str | None = Field(None, max_length=1000)
