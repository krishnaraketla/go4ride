from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import DocumentType, KycStatus, OnboardingStatus, VehicleType


class DriverApplicationListItem(BaseModel):
    driver_id: UUID
    name: str | None
    phone: str
    onboarding_status: OnboardingStatus
    kyc_status: KycStatus
    vehicle_make: str | None
    vehicle_model: str | None
    vehicle_plate: str | None
    documents_count: int
    submitted_at: datetime | None


class DriverApplicationListResponse(BaseModel):
    applications: list[DriverApplicationListItem]
    total: int
    page: int
    limit: int


class AdminDocumentItem(BaseModel):
    id: UUID
    document_type: DocumentType
    status: str
    rejection_reason: str | None
    created_at: datetime
    view_url: str


class AdminVehiclePhotos(BaseModel):
    front: str | None = None
    back: str | None = None
    left: str | None = None
    right: str | None = None


class DriverApplicationDetailResponse(BaseModel):
    driver_id: UUID
    name: str | None
    phone: str
    onboarding_status: OnboardingStatus
    kyc_status: KycStatus
    kyc_rejection_reason: str | None
    vehicle_type: VehicleType | None
    vehicle_make: str | None
    vehicle_model: str | None
    vehicle_year: int | None
    vehicle_plate: str | None
    vehicle_color: str | None
    city_slug: str | None
    city_name: str | None
    vehicle_photos: AdminVehiclePhotos
    face_verification_url: str | None
    face_verification_completed: bool
    documents: list[AdminDocumentItem]


class DriverApplicationActionResponse(BaseModel):
    driver_id: UUID
    onboarding_status: OnboardingStatus
    kyc_status: KycStatus


class RejectDriverApplicationRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255)
