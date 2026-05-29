from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RequestOTPRequest(BaseModel):
    """Single-step OTP request — used for both first-time sign-up and returning login."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"phone": "9876543210"}]},
    )

    phone: str = Field(..., min_length=10, max_length=15, examples=["9876543210"])


class VerifyOTPRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "phone": "9876543210",
                    "code": "123456",
                    "name": "Ravi Kumar",
                }
            ]
        },
    )

    phone: str = Field(..., min_length=10, max_length=15)
    code: str = Field(..., min_length=4, max_length=8)
    # Optional onboarding fields only used the first time the rider signs in.
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
    is_new_user: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class OTPSentData(BaseModel):
    expires_in_minutes: int
    is_new_user: bool
    debug_otp: str | None = None


class MeResponse(BaseModel):
    id: str
    phone: str
    name: str | None
    role: str
