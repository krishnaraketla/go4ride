from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import DocumentStatus, DocumentType, DriverStatus, KycStatus


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class DriverRequestOtpRequest(BaseModel):
    phone_number: str = Field(..., examples=["9876543210"], description="Mobile number without country code")
    country_code: str = Field(..., examples=["+91"], description="Country dial code e.g. +91 for India")
    device_id: str = Field(..., description="Unique device identifier for fraud detection")
    platform: str = Field(..., examples=["ios", "android"], description="ios or android")


class DriverRequestOtpResponse(BaseModel):
    success: bool = True
    message: str
    session_token: str | None = None
    otp_expires_in: int = Field(..., description="OTP validity in seconds")
    masked_phone: str = Field(..., description="Masked phone e.g. +91 ****3210")
    resend_allowed_after: int = Field(default=60, description="Seconds before resend is allowed")
    is_new_user: bool
    debug_otp: str | None = Field(default=None, description="Only present when OTP_DEBUG=true in .env")


class DriverVerifyOtpRequest(BaseModel):
    phone_number: str = Field(..., examples=["9876543210"], description="Mobile number without country code")
    country_code: str = Field(..., examples=["+91"], description="Country dial code e.g. +91")
    otp: str = Field(..., description="OTP received via SMS")
    device_id: str = Field(..., description="Unique device identifier")
    name: str | None = None
    fcm_token: str | None = None
    platform: str | None = None


class DriverBasicProfile(BaseModel):
    name: str | None
    phone: str
    avatar_url: str | None = None


class DriverAuthResponse(BaseModel):
    success: bool = True
    driver_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    token_expires_in: int = Field(default=900, description="Access token validity in seconds")
    is_new_driver: bool
    onboarding_status: str = Field(
        default="pending",
        description="pending = no profile yet, complete = profile exists",
    )
    profile: DriverBasicProfile


class DriverRefreshRequest(BaseModel):
    refresh_token: str


class DriverRefreshResponse(BaseModel):
    success: bool = True
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    token_expires_in: int = Field(default=900, description="Access token validity in seconds")
    refresh_token_expires_in: int = Field(default=604800, description="Refresh token validity in seconds")


class DriverLogoutRequest(BaseModel):
    refresh_token: str


class DriverLogoutResponse(BaseModel):
    success: bool = True
    message: str
    driver_status_set_to: str
    logged_out_at: datetime


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class DriverProfileResponse(BaseModel):
    driver_id: UUID
    name: str | None
    phone: str
    vehicle_model: str
    vehicle_plate: str
    vehicle_color: str
    ride_type_slug: str | None
    driver_status: DriverStatus
    kyc_status: KycStatus
    rating: Decimal | None
    total_rides: int

    model_config = {"from_attributes": True}


class UpdateDriverProfileRequest(BaseModel):
    name: str | None = None
    vehicle_model: str | None = None
    vehicle_plate: str | None = None
    vehicle_color: str | None = None
    ride_type_slug: str | None = None


class DriverEarningsResponse(BaseModel):
    today: Decimal
    this_week: Decimal
    this_month: Decimal
    total: Decimal
    currency: str


class DriverStatsResponse(BaseModel):
    total_rides: int
    completed_rides: int
    cancelled_rides: int
    acceptance_rate: float
    rating: Decimal | None


# ---------------------------------------------------------------------------
# Availability / Location
# ---------------------------------------------------------------------------

class DriverGoOnlineRequest(BaseModel):
    lat: Decimal = Field(..., ge=-90, le=90)
    lng: Decimal = Field(..., ge=-180, le=180)


class DriverAvailabilityResponse(BaseModel):
    driver_status: DriverStatus
    message: str


class UpdateLocationRequest(BaseModel):
    lat: Decimal = Field(..., ge=-90, le=90)
    lng: Decimal = Field(..., ge=-180, le=180)


class UpdateLocationResponse(BaseModel):
    lat: Decimal
    lng: Decimal
    updated: bool


# ---------------------------------------------------------------------------
# Rides
# ---------------------------------------------------------------------------

class RiderSummary(BaseModel):
    id: UUID
    name: str | None
    phone: str


class DriverRideResponse(BaseModel):
    id: UUID
    status: str
    pickup_lat: Decimal
    pickup_lng: Decimal
    pickup_address: str
    drop_lat: Decimal
    drop_lng: Decimal
    drop_address: str
    estimated_fare: Decimal
    final_fare: Decimal | None
    distance_km: Decimal | None
    duration_min: Decimal | None
    surge_multiplier: Decimal
    ride_type_slug: str | None
    start_otp: str | None
    requested_at: datetime
    driver_assigned_at: datetime | None
    driver_arrived_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    rider: RiderSummary | None

    model_config = {"from_attributes": True}


class AcceptRideRequest(BaseModel):
    ride_id: UUID


class AcceptRideResponse(BaseModel):
    ride_id: UUID
    status: str
    message: str


class RejectRideResponse(BaseModel):
    ride_id: UUID
    status: str
    message: str


class StartRideRequest(BaseModel):
    otp: str = Field(..., min_length=6, max_length=6)


class CompleteRideResponse(BaseModel):
    ride_id: UUID
    status: str
    final_fare: Decimal
    message: str


class DriverRideHistoryResponse(BaseModel):
    rides: list[DriverRideResponse]
    total: int
    page: int
    limit: int


# ---------------------------------------------------------------------------
# Documents / KYC
# ---------------------------------------------------------------------------

class DocumentUploadUrlRequest(BaseModel):
    document_type: DocumentType
    content_type: str = Field(
        default="image/jpeg",
        examples=["image/jpeg", "image/png", "application/pdf"],
    )


class DocumentUploadUrlResponse(BaseModel):
    upload_url: str
    file_key: str
    expires_in: int = 900


class ConfirmDocumentUploadRequest(BaseModel):
    document_type: DocumentType
    file_key: str


class DocumentResponse(BaseModel):
    id: UUID
    document_type: DocumentType
    status: DocumentStatus
    rejection_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class KycStatusResponse(BaseModel):
    kyc_status: KycStatus
    documents: list[DocumentResponse]
