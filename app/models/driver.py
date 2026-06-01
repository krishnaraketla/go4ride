import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DocumentStatus, DocumentType, DriverStatus, KycStatus


class DriverProfile(Base):
    __tablename__ = "driver_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    vehicle_model: Mapped[str] = mapped_column(String(64))
    vehicle_plate: Mapped[str] = mapped_column(String(32))
    vehicle_color: Mapped[str] = mapped_column(String(32))
    current_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    current_lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)

    # Phase-2 driver fields
    ride_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride_types.id"), nullable=True
    )
    driver_status: Mapped[DriverStatus] = mapped_column(
        Enum(DriverStatus), default=DriverStatus.offline
    )
    kyc_status: Mapped[KycStatus] = mapped_column(
        Enum(KycStatus), default=KycStatus.pending
    )
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    total_rides: Mapped[int] = mapped_column(default=0)

    user: Mapped["User"] = relationship()  # type: ignore[name-defined]
    ride_type: Mapped["RideType"] = relationship()  # type: ignore[name-defined]
    documents: Mapped[list["DriverDocument"]] = relationship(back_populates="profile")


class DriverDocument(Base):
    __tablename__ = "driver_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver_profiles.user_id"), index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType))
    file_key: Mapped[str] = mapped_column(String(512))
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.pending
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped["DriverProfile"] = relationship(back_populates="documents")
