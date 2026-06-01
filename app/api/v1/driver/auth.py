from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.db.session import get_db
from app.models.user import User
from app.schemas.driver import (
    DriverAuthResponse,
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


@router.post("/request-otp", response_model=DriverRequestOtpResponse)
async def request_otp(
    body: DriverRequestOtpRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    debug_otp, expires_minutes, is_new_user = await driver_auth_service.send_driver_auth_otp(
        db, body.phone
    )
    await db.commit()
    return DriverRequestOtpResponse(
        message="OTP sent",
        expires_in_minutes=expires_minutes,
        is_new_user=is_new_user,
        debug_otp=debug_otp,
    )


@router.post("/verify-otp", response_model=DriverAuthResponse)
async def verify_otp(
    body: DriverVerifyOtpRequest,
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
    await db.commit()
    return DriverAuthResponse(
        access_token=access,
        refresh_token=refresh,
        is_new_user=is_new,
        driver_id=user.id,
        name=user.name,
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
