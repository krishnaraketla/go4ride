from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import DocumentStatus, DocumentType, DriverStatus, KycStatus


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class DriverRequestOtpRequest(BaseModel):
    phone: str = Field(..., examples=["9876543210"])


class DriverRequestOtpResponse(BaseModel):
    message: str
    expires_in_minutes: int
    is_new_user: bool
    debug_otp: str | None = None


class DriverVerifyOtpRequest(BaseModel):
    phone: str
    code: str
    name: str | None = None
    fcm_token: str | None = None
    platform: str | None = None


class DriverAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_new_user: bool
    driver_id: UUID
    name: str | None


class DriverRefreshRequest(BaseModel):
    refresh_token: str


class DriverRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class DriverLogoutRequest(BaseModel):
    refresh_token: str


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
