from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import DocumentStatus, DocumentType, DriverStatus, KycStatus, OnboardingStatus, VehicleType


# ---------------------------------------------------------------------------
# Auth — request bodies reuse app.schemas.auth.RequestOTPRequest / VerifyOTPRequest
# ---------------------------------------------------------------------------

class DriverBasicProfile(BaseModel):
    name: str | None
    phone: str
    avatar_url: str | None = None


class DriverAuthResponse(BaseModel):
    driver_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    token_expires_in: int = Field(default=900, description="Access token validity in seconds")
    is_new_driver: bool
    onboarding_status: OnboardingStatus = OnboardingStatus.step1
    profile_status: bool = False
    application_id: str | None = None
    kyc_rejection_reason: str | None = None
    profile: DriverBasicProfile


class DriverRefreshRequest(BaseModel):
    refresh_token: str


class DriverRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    token_expires_in: int = Field(default=900, description="Access token validity in seconds")
    refresh_token_expires_in: int = Field(default=604800, description="Refresh token validity in seconds")


class DriverLogoutRequest(BaseModel):
    refresh_token: str


class DriverLogoutResponse(BaseModel):
    driver_status_set_to: str
    logged_out_at: datetime


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class DriverProfileResponse(BaseModel):
    driver_id: UUID
    name: str | None
    phone: str
    vehicle_model: str | None
    vehicle_plate: str | None
    vehicle_color: str | None
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
# Profile Menu (Screen 10)
# ---------------------------------------------------------------------------

class MenuInbox(BaseModel):
    unread_count: int = 0


class MenuWallet(BaseModel):
    balance: float = 0.0
    currency: str = "INR"


class MenuSubscription(BaseModel):
    plan: str = "free"
    status: str = "inactive"
    expires_at: str | None = None


class MenuItem(BaseModel):
    key: str
    label: str
    badge: int | None = None
    visible: bool = True


class MenuProfileSummary(BaseModel):
    driver_id: str
    name: str | None
    avatar_url: str | None
    phone: str
    rating: float | None
    currency: str = "INR"


class ProfileMenuResponse(BaseModel):
    profile: MenuProfileSummary
    inbox: MenuInbox
    wallet: MenuWallet
    subscription: MenuSubscription
    menu_items: list[MenuItem]


# ---------------------------------------------------------------------------
# Availability / Location
# ---------------------------------------------------------------------------

class DriverStatusRequest(BaseModel):
    status: str = Field(..., examples=["online", "offline"])
    latitude: Decimal = Field(..., ge=-90, le=90)
    longitude: Decimal = Field(..., ge=-180, le=180)
    heading: float | None = Field(default=None, ge=0, le=360)


class DriverStatusResponse(BaseModel):
    driver_id: str
    status: str
    updated_at: datetime
    dispatch_pool: str
    message: str


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


class DriverRideSearchMeta(BaseModel):
    lat: Decimal
    lng: Decimal
    radius_km: float
    total: int


class DriverRideSearchItem(DriverRideResponse):
    pickup_distance_m: int
    pickup_eta_min: int | None = None


class DriverRideSearchResponse(BaseModel):
    rides: list[DriverRideSearchItem]
    search: DriverRideSearchMeta


# ---------------------------------------------------------------------------
# Onboarding — Vehicle
# ---------------------------------------------------------------------------

class VehiclePhotos(BaseModel):
    front: str = Field(..., min_length=1)
    back: str = Field(..., min_length=1)
    left: str = Field(..., min_length=1)
    right: str = Field(..., min_length=1)


class VehicleSubmitRequest(BaseModel):
    vehicle_type: VehicleType
    make: str = Field(..., examples=["Maruti", "Tata"])
    model: str = Field(..., examples=["Swift", "Nexon"])
    year: int = Field(..., ge=2000, le=2030, examples=[2022])
    plate_number: str = Field(..., examples=["TS09AB1234"])
    color: str = Field(..., examples=["White"])
    city_id: UUID
    photos: VehiclePhotos


class VehicleResponse(BaseModel):
    vehicle_id: str
    driver_id: str
    type: str
    make: str
    model: str
    year: int
    plate_number: str
    color: str
    photos: VehiclePhotos
    status: str


class VehicleSubmitResponse(BaseModel):
    vehicle: VehicleResponse
    onboarding_step: str = "submit_application"


# ---------------------------------------------------------------------------
# Onboarding — Submit Application
# ---------------------------------------------------------------------------

class VerificationProgress(BaseModel):
    documents_uploaded: bool
    vehicle_details_submitted: bool
    face_verification_completed: bool


class SubmitApplicationResponse(BaseModel):
    application_id: str
    onboarding_status: OnboardingStatus
    profile_status: bool
    estimated_review_time: str
    submitted_at: datetime
    message: str


class StepProgress(BaseModel):
    documents_complete: bool
    vehicle_complete: bool
    city_selected: bool
    vehicle_photos_complete: bool


class OnboardingStatusResponse(BaseModel):
    onboarding_status: OnboardingStatus
    profile_status: bool
    application_id: str | None
    kyc_rejection_reason: str | None
    face_verification_completed: bool
    estimated_review_time: str | None
    step_progress: StepProgress


class CityResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    state: str | None


class VehiclePhotoUploadUrlRequest(BaseModel):
    side: str = Field(..., examples=["front", "back", "left", "right"])
    content_type: str = Field(
        default="image/jpeg",
        examples=["image/jpeg", "image/png"],
    )


class FaceVerificationUploadUrlRequest(BaseModel):
    content_type: str = Field(
        default="image/jpeg",
        examples=["image/jpeg", "image/png"],
    )


class FaceVerificationConfirmRequest(BaseModel):
    file_key: str


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


class DocumentStatusItem(BaseModel):
    type: str
    label: str
    description: str
    status: str
    sides_required: list[str]
    uploaded_at: datetime | None
    rejection_reason: str | None


class OverallProgress(BaseModel):
    uploaded: int
    total: int
    percentage: int


class KycStatusResponse(BaseModel):
    kyc_status: KycStatus
    overall_progress: OverallProgress
    documents: list[DocumentStatusItem]
