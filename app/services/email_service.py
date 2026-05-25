import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import bad_request
from app.core.security import hash_otp, verify_otp
from app.models.enums import CreditTransactionType
from app.models.user import User
from app.models.wallet import CreditTransaction, EmailVerificationToken
from app.services.wallet_service import grant_credit


async def send_verification(db: AsyncSession, user: User) -> str | None:
    if not user.email:
        raise bad_request("Email required on profile", "EMAIL_REQUIRED")
    if user.email_verified_at is not None:
        raise bad_request("Email already verified", "EMAIL_ALREADY_VERIFIED")

    settings = get_settings()
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_otp(code),
            expires_at=expires,
        )
    )
    if settings.otp_debug:
        print(f"[email-verify] user={user.id} code={code}")
    return code if settings.otp_debug else None


async def verify_email(db: AsyncSession, user: User, code: str) -> User:
    if user.email_verified_at is not None:
        raise bad_request("Email already verified", "EMAIL_ALREADY_VERIFIED")

    result = await db.execute(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id)
        .order_by(EmailVerificationToken.created_at.desc())
        .limit(1)
    )
    token_row = result.scalar_one_or_none()
    if token_row is None or token_row.expires_at < datetime.now(timezone.utc):
        raise bad_request("Verification code expired or invalid", "EMAIL_VERIFY_INVALID")
    if not verify_otp(code, token_row.token_hash):
        raise bad_request("Verification code expired or invalid", "EMAIL_VERIFY_INVALID")

    user.email_verified_at = datetime.now(timezone.utc)

    # One-time email bonus
    existing_bonus = await db.execute(
        select(CreditTransaction).where(
            CreditTransaction.user_id == user.id,
            CreditTransaction.type == CreditTransactionType.email_bonus,
        )
    )
    if existing_bonus.scalar_one_or_none() is None:
        settings = get_settings()
        await grant_credit(
            db,
            user.id,
            settings.email_verify_bonus,
            CreditTransactionType.email_bonus,
            reference_id="email_verify",
        )
    return user
