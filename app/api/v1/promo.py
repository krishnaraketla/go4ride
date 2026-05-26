from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.models.wallet import PartnerLead
from app.schemas.wallet import (
    PartnerInterestRequest,
    PromoApplyRequest,
    PromoApplyResponse,
    ReferralResponse,
)
from app.services import wallet_service

router = APIRouter(tags=["promo"])


@router.post("/promo/apply", response_model=PromoApplyResponse)
async def apply_promo(
    body: PromoApplyRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Apply a promo code and credit the wallet (e.g. seed code `WELCOME5`)."""

    wallet, credited = await wallet_service.apply_promo_code(db, rider.id, body.code)
    return PromoApplyResponse(
        balance=wallet.balance,
        currency=wallet.currency,
        credited=credited,
        message="Promo applied successfully",
    )


@router.get("/referral", response_model=ReferralResponse)
async def get_referral(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get the rider's referral code and reward amount."""

    settings = get_settings()
    code = await wallet_service.ensure_referral_code(db, rider)
    return ReferralResponse(
        code=code,
        reward_amount=settings.referral_bonus,
        currency=settings.default_currency,
    )


@router.post("/partner/interest")
async def partner_interest(
    body: PartnerInterestRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Record partner/franchise interest (stub)."""

    db.add(PartnerLead(user_id=rider.id, message=body.message))
    return {"message": "Interest recorded"}
