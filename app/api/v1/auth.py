from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.enums import OTPPurpose, UserRole
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    OTPSentResponse,
    RegisterRequest,
    TokenResponse,
    VerifyOTPRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=OTPSentResponse)
async def register(body: RegisterRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    debug_otp, expires = await auth_service.send_registration_otp(db, body.phone, body.name)
    return OTPSentResponse(message="OTP sent", expires_in_minutes=expires, debug_otp=debug_otp)


@router.post("/login", response_model=OTPSentResponse)
async def login(body: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    debug_otp, expires = await auth_service.send_login_otp(db, body.phone)
    return OTPSentResponse(message="OTP sent", expires_in_minutes=expires, debug_otp=debug_otp)


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(body: VerifyOTPRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    purpose = OTPPurpose(body.purpose)
    user, access, refresh = await auth_service.verify_otp_and_login(
        db,
        body.phone,
        body.code,
        purpose,
        name=body.name,
        fcm_token=body.fcm_token,
        platform=body.platform,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=user.id,
        role=user.role.value,
    )


@router.post("/logout")
async def logout(body: LogoutRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    await auth_service.logout(db, body.refresh_token)
    return {"message": "Logged out"}


@router.get("/me")
async def me(user: Annotated[User, Depends(get_current_user)]):
    return {"id": str(user.id), "phone": user.phone, "name": user.name, "role": user.role.value}
