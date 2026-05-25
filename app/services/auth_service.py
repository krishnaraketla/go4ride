from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import bad_request, conflict, too_many_requests, unauthorized
from app.core.redis import check_rate_limit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_otp,
    hash_refresh_token,
    verify_otp,
)
from app.models.enums import OTPPurpose, UserRole
from app.models.user import OTPVerification, RefreshToken, User, UserDevice
from app.services.otp_service import send_otp_sms


async def send_registration_otp(db: AsyncSession, phone: str, name: str) -> tuple[str | None, int]:
    if await check_rate_limit(f"otp:{phone}", limit=5, window_seconds=3600):
        raise too_many_requests("Too many OTP requests")

    result = await db.execute(select(User).where(User.phone == phone))
    if result.scalar_one_or_none():
        raise conflict("Phone already registered", "PHONE_EXISTS")

    return await _create_otp(db, phone, OTPPurpose.register)


async def send_login_otp(db: AsyncSession, phone: str) -> tuple[str | None, int]:
    if await check_rate_limit(f"otp:{phone}", limit=5, window_seconds=3600):
        raise too_many_requests("Too many OTP requests")

    result = await db.execute(select(User).where(User.phone == phone, User.role == UserRole.rider))
    user = result.scalar_one_or_none()
    if user is None:
        raise bad_request("User not found", "USER_NOT_FOUND")
    if user.is_blocked:
        raise bad_request("Account is blocked", "ACCOUNT_BLOCKED")

    return await _create_otp(db, phone, OTPPurpose.login)


async def _create_otp(db: AsyncSession, phone: str, purpose: OTPPurpose) -> tuple[str | None, int]:
    settings = get_settings()
    code = generate_otp()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)
    otp = OTPVerification(
        phone=phone,
        code_hash=hash_otp(code),
        purpose=purpose,
        expires_at=expires,
    )
    db.add(otp)
    await send_otp_sms(phone, code)
    debug_otp = code if settings.otp_debug else None
    return debug_otp, settings.otp_expire_minutes


async def verify_otp_and_login(
    db: AsyncSession,
    phone: str,
    code: str,
    purpose: OTPPurpose,
    name: str | None = None,
    fcm_token: str | None = None,
    platform: str | None = None,
    referral_code: str | None = None,
) -> tuple[User, str, str]:
    result = await db.execute(
        select(OTPVerification)
        .where(OTPVerification.phone == phone, OTPVerification.purpose == purpose)
        .order_by(OTPVerification.created_at.desc())
        .limit(1)
    )
    otp_record = result.scalar_one_or_none()
    if otp_record is None or otp_record.expires_at < datetime.now(timezone.utc):
        raise bad_request("OTP expired or invalid", "OTP_INVALID")
    if not verify_otp(code, otp_record.code_hash):
        raise bad_request("OTP expired or invalid", "OTP_INVALID")

    user_result = await db.execute(select(User).where(User.phone == phone))
    user = user_result.scalar_one_or_none()

    if purpose == OTPPurpose.register:
        if user is not None:
            raise conflict("Phone already registered", "PHONE_EXISTS")
        if not name:
            raise bad_request("Name required for registration", "NAME_REQUIRED")
        user = User(phone=phone, name=name, role=UserRole.rider)
        db.add(user)
        await db.flush()
        from app.services.wallet_service import apply_referral_on_register

        await apply_referral_on_register(db, user, referral_code)
    else:
        if user is None or user.role != UserRole.rider:
            raise bad_request("User not found", "USER_NOT_FOUND")

    if fcm_token:
        device = UserDevice(user_id=user.id, fcm_token=fcm_token, platform=platform)
        db.add(device)

    access = create_access_token(user.id, user.role.value)
    refresh = create_refresh_token(user.id, user.role.value)
    settings = get_settings()
    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days),
    )
    db.add(refresh_record)
    return user, access, refresh


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> tuple[User, str, str]:
    from app.core.security import verify_token

    try:
        payload = verify_token(refresh_token, "refresh")
    except ValueError as exc:
        raise unauthorized("Invalid refresh token", "INVALID_REFRESH_TOKEN") from exc

    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.revoked.is_(False))
    )
    record = result.scalar_one_or_none()
    if record is None or record.expires_at < datetime.now(timezone.utc):
        raise unauthorized("Invalid refresh token", "INVALID_REFRESH_TOKEN")

    user_id = UUID(payload["sub"])
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None or user.is_blocked:
        raise unauthorized("Invalid refresh token", "INVALID_REFRESH_TOKEN")

    record.revoked = True
    access = create_access_token(user.id, user.role.value)
    new_refresh = create_refresh_token(user.id, user.role.value)
    settings = get_settings()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(new_refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days),
        )
    )
    return user, access, new_refresh


async def logout(db: AsyncSession, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    record = result.scalar_one_or_none()
    if record:
        record.revoked = True
