from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    LogoutRequest,
    MeResponse,
    OTPSentData,
    RefreshRequest,
    RequestOTPRequest,
    TokenResponse,
    VerifyOTPRequest,
)
from app.schemas.response import ApiResponse, ok
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-otp", response_model=ApiResponse[OTPSentData])
async def request_otp(body: RequestOTPRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Send an OTP to the given phone. Works for both new and returning riders.

    The client should follow up with `POST /auth/verify-otp`. `is_new_user`
    tells the UI whether to show an onboarding step (e.g. ask for name) after
    verification.
    """

    debug_otp, expires, is_new_user = await auth_service.send_auth_otp(db, body.phone)
    return ok(
        OTPSentData(
            expires_in_minutes=expires,
            is_new_user=is_new_user,
            debug_otp=debug_otp,
        ),
        message="OTP sent",
    )


@router.post("/verify-otp", response_model=ApiResponse[TokenResponse])
async def verify_otp(body: VerifyOTPRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Verify OTP and return JWTs. Creates the rider account if first-time."""

    user, access, refresh, is_new_user = await auth_service.verify_otp_and_login(
        db,
        body.phone,
        body.code,
        name=body.name,
        fcm_token=body.fcm_token,
        platform=body.platform,
        referral_code=body.referral_code,
    )
    return ok(
        TokenResponse(
            access_token=access,
            refresh_token=refresh,
            user_id=user.id,
            role=user.role.value,
            is_new_user=is_new_user,
        ),
        message="Signed in successfully",
    )


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh(body: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Exchange a refresh token for a new JWT pair."""

    user, access, refresh_token = await auth_service.refresh_tokens(db, body.refresh_token)
    return ok(
        TokenResponse(
            access_token=access,
            refresh_token=refresh_token,
            user_id=user.id,
            role=user.role.value,
        ),
        message="Token refreshed",
    )


@router.post("/logout", response_model=ApiResponse[None])
async def logout(body: LogoutRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Revoke the refresh token (client should discard both tokens)."""

    await auth_service.logout(db, body.refresh_token)
    return ok(message="Logged out")


@router.get("/me", response_model=ApiResponse[MeResponse])
async def me(user: Annotated[User, Depends(get_current_user)]):
    """Return the authenticated user's id, phone, name, and role."""

    return ok(
        MeResponse(
            id=str(user.id),
            phone=user.phone,
            name=user.name,
            role=user.role.value,
        ),
        message="User profile retrieved",
    )
