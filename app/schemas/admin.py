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
    vehicle_model: str
    vehicle_plate: str
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


class DriverApplicationDetailResponse(BaseModel):
    driver_id: UUID
    name: str | None
    phone: str
    onboarding_status: OnboardingStatus
    kyc_status: KycStatus
    vehicle_type: VehicleType | None
    vehicle_make: str | None
    vehicle_model: str
    vehicle_year: int | None
    vehicle_plate: str
    vehicle_color: str
    documents: list[AdminDocumentItem]


class DriverApplicationActionResponse(BaseModel):
    driver_id: UUID
    onboarding_status: OnboardingStatus
    kyc_status: KycStatus


class RejectDriverApplicationRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255)
