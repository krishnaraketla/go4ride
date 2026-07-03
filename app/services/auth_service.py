from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import bad_request, too_many_requests, unauthorized
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
from app.services.otp_bypass import is_otp_bypass, is_otp_bypass_phone
from app.services.otp_service import send_otp_sms

# Single internal purpose for the unified phone-OTP flow. The DB enum keeps
# both legacy values so no migration is required; we just always write `login`
# and treat verify-otp as "auth attempt" regardless of whether the user exists.
_AUTH_PURPOSE = OTPPurpose.login


async def send_auth_otp(db: AsyncSession, phone: str) -> tuple[str | None, int, bool]:
    """Send an OTP for a phone number, creating the user lazily on verify.

    Returns ``(debug_otp, expires_in_minutes, is_new_user)``. ``is_new_user`` is
    a hint for the client UI; the actual account is created in
    :func:`verify_otp_and_login`.
    """

    if await check_rate_limit(f"otp:{phone}", limit=5, window_seconds=3600):
        raise too_many_requests("Too many OTP requests")

    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()
    if user is not None and user.is_blocked:
        raise bad_request("Account is blocked", "ACCOUNT_BLOCKED")

    is_new_user = user is None
    settings = get_settings()
    if is_otp_bypass_phone(phone):
        # Pre-seeded test phones: no SMS, no OTP row; verify with otp_bypass_code.
        return None, settings.otp_expire_minutes, is_new_user

    debug_otp, expires_minutes = await _create_otp(db, phone, _AUTH_PURPOSE)
    return debug_otp, expires_minutes, is_new_user


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
    name: str | None = None,
    fcm_token: str | None = None,
    platform: str | None = None,
    referral_code: str | None = None,
) -> tuple[User, str, str, bool]:
    """Verify the latest OTP for ``phone``; create the rider account if missing.

    Returns ``(user, access_token, refresh_token, is_new_user)``.
    """

    if not is_otp_bypass(phone, code):
        result = await db.execute(
            select(OTPVerification)
            .where(OTPVerification.phone == phone, OTPVerification.purpose == _AUTH_PURPOSE)
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

    is_new_user = user is None
    if is_new_user:
        user = User(phone=phone, name=name, role=UserRole.rider)
        db.add(user)
        await db.flush()
        from app.services.wallet_service import apply_referral_on_register

        await apply_referral_on_register(db, user, referral_code)
    else:
        if user.is_blocked:
            raise bad_request("Account is blocked", "ACCOUNT_BLOCKED")
        if user.role != UserRole.rider:
            raise bad_request("User not found", "USER_NOT_FOUND")
        # Returning rider: only fill in name if it's still missing.
        if name and not user.name:
            user.name = name

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
    return user, access, refresh, is_new_user


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
