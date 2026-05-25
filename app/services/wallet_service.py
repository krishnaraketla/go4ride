import secrets
import string
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import bad_request, conflict, not_found
from app.models.enums import CreditTransactionType
from app.models.user import User
from app.models.wallet import CreditTransaction, PromoCode, PromoRedemption, Wallet


async def get_or_create_wallet(db: AsyncSession, user_id: UUID) -> Wallet:
    result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = result.scalar_one_or_none()
    if wallet is None:
        settings = get_settings()
        wallet = Wallet(user_id=user_id, balance=Decimal("0"), currency=settings.default_currency)
        db.add(wallet)
        await db.flush()
    return wallet


async def get_wallet_balance(db: AsyncSession, user_id: UUID) -> tuple[Decimal, str]:
    wallet = await get_or_create_wallet(db, user_id)
    return wallet.balance, wallet.currency


async def grant_credit(
    db: AsyncSession,
    user_id: UUID,
    amount: Decimal,
    tx_type: CreditTransactionType,
    reference_id: str | None = None,
) -> Wallet:
    if amount <= 0:
        raise bad_request("Credit amount must be positive", "INVALID_CREDIT_AMOUNT")
    wallet = await get_or_create_wallet(db, user_id)
    wallet.balance += amount
    db.add(
        CreditTransaction(
            user_id=user_id,
            amount=amount,
            type=tx_type,
            reference_id=reference_id,
        )
    )
    return wallet


def _generate_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


async def ensure_referral_code(db: AsyncSession, user: User) -> str:
    if user.referral_code:
        return user.referral_code
    for _ in range(10):
        code = _generate_referral_code()
        existing = await db.execute(select(User).where(User.referral_code == code))
        if existing.scalar_one_or_none() is None:
            user.referral_code = code
            await db.flush()
            return code
    raise bad_request("Could not generate referral code", "REFERRAL_CODE_FAILED")


async def apply_referral_on_register(
    db: AsyncSession, new_user: User, referral_code: str | None
) -> None:
    if not referral_code or new_user.referred_by_user_id is not None:
        return
    result = await db.execute(select(User).where(User.referral_code == referral_code.upper()))
    referrer = result.scalar_one_or_none()
    if referrer is None or referrer.id == new_user.id:
        return
    new_user.referred_by_user_id = referrer.id
    settings = get_settings()
    await grant_credit(
        db,
        referrer.id,
        settings.referral_bonus,
        CreditTransactionType.referral,
        reference_id=str(new_user.id),
    )


async def apply_promo_code(db: AsyncSession, user_id: UUID, code: str) -> tuple[Wallet, Decimal]:
    normalized = code.strip().upper()
    result = await db.execute(select(PromoCode).where(PromoCode.code == normalized))
    promo = result.scalar_one_or_none()
    if promo is None or not promo.is_active:
        raise not_found("Promo code not found", "PROMO_NOT_FOUND")
    now = datetime.now(timezone.utc)
    if promo.expires_at and promo.expires_at < now:
        raise bad_request("Promo code expired", "PROMO_EXPIRED")
    if promo.max_uses is not None and promo.use_count >= promo.max_uses:
        raise bad_request("Promo code exhausted", "PROMO_EXHAUSTED")

    redeemed = await db.execute(
        select(PromoRedemption).where(
            PromoRedemption.user_id == user_id, PromoRedemption.promo_code_id == promo.id
        )
    )
    if redeemed.scalar_one_or_none():
        raise conflict("Promo already redeemed", "PROMO_ALREADY_REDEEMED")

    db.add(PromoRedemption(user_id=user_id, promo_code_id=promo.id))
    promo.use_count += 1
    wallet = await grant_credit(
        db, user_id, promo.amount, CreditTransactionType.promo, reference_id=promo.code
    )
    return wallet, promo.amount
