from uuid import UUID

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    name: str = Field(..., min_length=1, max_length=255)


class LoginRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)


class VerifyOTPRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    code: str = Field(..., min_length=4, max_length=8)
    purpose: str = Field(..., pattern="^(login|register)$")
    name: str | None = Field(None, max_length=255)
    fcm_token: str | None = None
    platform: str | None = None
    referral_code: str | None = Field(None, max_length=16)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: UUID
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class OTPSentResponse(BaseModel):
    message: str
    expires_in_minutes: int
    debug_otp: str | None = None
