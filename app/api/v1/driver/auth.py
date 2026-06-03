from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import get_current_driver
from app.db.session import get_db
from app.models.driver import DriverProfile
from app.models.user import User
from app.schemas.driver import (
    DriverAuthResponse,
    DriverBasicProfile,
    DriverLogoutRequest,
    DriverRefreshRequest,
    DriverRefreshResponse,
    DriverRequestOtpRequest,
    DriverRequestOtpResponse,
    DriverVerifyOtpRequest,
)
from app.services import driver_auth_service
from app.services.auth_service import logout, refresh_tokens

router = APIRouter(prefix="/auth", tags=["Driver Auth"])


def _mask_phone(country_code: str, phone_number: str) -> str:
    """Return masked phone e.g. +91 ****3210"""
    visible = phone_number[-4:]
    masked = "*" * (len(phone_number) - 4)
    return f"{country_code} {masked}{visible}"


@router.post("/request-otp", response_model=DriverRequestOtpResponse)
async def request_otp(
    body: DriverRequestOtpRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Combine country_code + phone_number → "+919876543210"
    full_phone = f"{body.country_code}{body.phone_number}"

    debug_otp, expires_minutes, is_new_user = await driver_auth_service.send_driver_auth_otp(
        db, full_phone
    )
    await db.commit()

    settings = get_settings()
    return DriverRequestOtpResponse(
        success=True,
        message="OTP sent successfully",
        otp_expires_in=expires_minutes * 60,          # convert minutes → seconds
        masked_phone=_mask_phone(body.country_code, body.phone_number),
        resend_allowed_after=60,
        is_new_user=is_new_user,
        debug_otp=debug_otp if settings.otp_debug else None,
    )


@router.post("/verify-otp", response_model=DriverAuthResponse)
async def verify_otp(
    body: DriverVerifyOtpRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    full_phone = f"{body.country_code}{body.phone_number}"
    user, access, refresh, is_new = await driver_auth_service.verify_otp_and_login_driver(
        db,
        phone=full_phone,
        code=body.otp,
        name=body.name,
        fcm_token=body.fcm_token,
        platform=body.platform,
    )

    # Check if driver has completed onboarding (profile exists)
    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    onboarding_status = "complete" if profile is not None else "pending"

    settings = get_settings()
    await db.commit()

    return DriverAuthResponse(
        success=True,
        driver_id=str(user.id),
        access_token=access,
        refresh_token=refresh,
        token_expires_in=settings.jwt_access_expire_minutes * 60,
        is_new_driver=is_new,
        onboarding_status=onboarding_status,
        profile=DriverBasicProfile(
            name=user.name,
            phone=full_phone,
            avatar_url=getattr(user, "avatar_url", None),
        ),
    )


@router.post("/refresh", response_model=DriverRefreshResponse)
async def refresh(
    body: DriverRefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user, access, new_refresh = await refresh_tokens(db, body.refresh_token)
    await db.commit()
    return DriverRefreshResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def driver_logout(
    body: DriverLogoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_driver)],
):
    await logout(db, body.refresh_token)
    await db.commit()
