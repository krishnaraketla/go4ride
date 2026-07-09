"""Driver-specific auth service.

Mirrors the rider auth flow but creates accounts with role=UserRole.driver
and auto-creates a DriverProfile at step1 for new drivers.
"""

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
    hash_refresh_token,
    verify_otp,
)
from app.models.driver import DriverProfile
from app.models.enums import OnboardingStatus, OTPPurpose, UserRole
from app.models.user import OTPVerification, RefreshToken, User, UserDevice
from app.services.auth_service import _create_otp
from app.services.otp_bypass import is_otp_bypass, is_otp_bypass_phone

_AUTH_PURPOSE = OTPPurpose.login


async def send_driver_auth_otp(db: AsyncSession, phone: str) -> tuple[str | None, int, bool]:
    """Send an OTP for a driver phone number.

    Returns ``(debug_otp, expires_in_minutes, is_new_user)``.
    """
    if not is_otp_bypass_phone(phone) and await check_rate_limit(
        f"otp:{phone}", limit=5, window_seconds=3600
    ):
        raise too_many_requests("Too many OTP requests")

    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()

    if user is not None and user.is_blocked:
        raise bad_request("Account is blocked", "ACCOUNT_BLOCKED")

    # Allow only if the user doesn't exist yet OR is already a driver.
    # Riders cannot log in to the driver app with the same phone.
    if user is not None and user.role != UserRole.driver:
        raise bad_request("This phone is registered as a rider account", "WRONG_ROLE")

    is_new_user = user is None
    settings = get_settings()
    if is_otp_bypass_phone(phone):
        # Pre-seeded test phones: no SMS, no OTP row; verify with otp_bypass_code.
        return None, settings.otp_expire_minutes, is_new_user

    debug_otp, expires_minutes = await _create_otp(db, phone, _AUTH_PURPOSE)
    return debug_otp, expires_minutes, is_new_user


async def verify_otp_and_login_driver(
    db: AsyncSession,
    phone: str,
    code: str,
    name: str | None = None,
    fcm_token: str | None = None,
    platform: str | None = None,
) -> tuple[User, str, str, bool]:
    """Verify OTP and log in (or register) a driver.

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
        user = User(phone=phone, name=name, role=UserRole.driver)
        db.add(user)
        await db.flush()
        db.add(DriverProfile(user_id=user.id, onboarding_status=OnboardingStatus.step1))
    else:
        if user.is_blocked:
            raise bad_request("Account is blocked", "ACCOUNT_BLOCKED")
        if user.role != UserRole.driver:
            raise bad_request("This phone is registered as a rider account", "WRONG_ROLE")
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
