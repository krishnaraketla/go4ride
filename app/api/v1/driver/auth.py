from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_driver
from app.db.session import get_db
from app.models.driver import DriverProfile
from app.models.enums import OnboardingStatus
from app.models.user import User
from app.schemas.auth import OTPSentData, RequestOTPRequest, VerifyOTPRequest
from app.schemas.driver import (
    DriverAuthResponse,
    DriverBasicProfile,
    DriverLogoutRequest,
    DriverLogoutResponse,
    DriverRefreshRequest,
    DriverRefreshResponse,
)
from app.schemas.response import ApiResponse, ok
from app.services import driver_auth_service
from app.services.auth_service import logout, refresh_tokens
from app.services.driver_onboarding_service import profile_status_for

router = APIRouter(prefix="/auth", tags=["Driver Auth"])


async def _get_or_create_profile(db: AsyncSession, user: User) -> DriverProfile:
    result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = DriverProfile(user_id=user.id, onboarding_status=OnboardingStatus.step1)
        db.add(profile)
        await db.flush()
    return profile


@router.post("/request-otp", response_model=ApiResponse[OTPSentData])
async def request_otp(body: RequestOTPRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    debug_otp, expires_minutes, is_new_user = await driver_auth_service.send_driver_auth_otp(
        db, body.phone
    )
    return ok(
        OTPSentData(
            expires_in_minutes=expires_minutes,
            is_new_user=is_new_user,
            debug_otp=debug_otp,
        ),
        message="OTP sent",
    )


@router.post("/verify-otp", response_model=ApiResponse[DriverAuthResponse])
async def verify_otp(
    body: VerifyOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user, access, refresh, is_new = await driver_auth_service.verify_otp_and_login_driver(
        db,
        phone=body.phone,
        code=body.code,
        name=body.name,
        fcm_token=body.fcm_token,
        platform=body.platform,
    )

    profile = await _get_or_create_profile(db, user)
    settings = get_settings()
    await db.commit()

    return ok(
        DriverAuthResponse(
            driver_id=str(user.id),
            access_token=access,
            refresh_token=refresh,
            token_expires_in=settings.jwt_access_expire_minutes * 60,
            is_new_driver=is_new,
            onboarding_status=profile.onboarding_status,
            profile_status=profile_status_for(profile),
            application_id=profile.application_id,
            kyc_rejection_reason=profile.kyc_rejection_reason,
            profile=DriverBasicProfile(
                name=user.name,
                phone=body.phone,
                avatar_url=getattr(user, "avatar_url", None),
            ),
        ),
        message="Signed in successfully",
    )


@router.post("/refresh", response_model=ApiResponse[DriverRefreshResponse])
async def refresh(
    body: DriverRefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user, access, new_refresh = await refresh_tokens(db, body.refresh_token)
    settings = get_settings()
    await db.commit()
    return ok(
        DriverRefreshResponse(
            access_token=access,
            refresh_token=new_refresh,
            token_expires_in=settings.jwt_access_expire_minutes * 60,
            refresh_token_expires_in=settings.jwt_refresh_expire_days * 24 * 60 * 60,
        ),
        message="Token refreshed",
    )


@router.post("/logout", response_model=ApiResponse[DriverLogoutResponse])
async def driver_logout(
    body: DriverLogoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    await logout(db, body.refresh_token)

    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver.id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is not None:
        from app.models.enums import DriverStatus
        profile.driver_status = DriverStatus.offline

    logged_out_at = datetime.now(timezone.utc)
    await db.commit()

    return ok(
        DriverLogoutResponse(
            driver_status_set_to="offline",
            logged_out_at=logged_out_at,
        ),
        message="Logged out successfully",
    )
