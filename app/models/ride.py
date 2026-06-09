import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RideStatus


class RideType(Base):
    __tablename__ = "ride_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class FareRule(Base):
    __tablename__ = "fare_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ride_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ride_types.id"))
    base_fare: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    per_km_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    per_min_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    minimum_fare: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    is_active: Mapped[bool] = mapped_column(default=True)

    ride_type: Mapped["RideType"] = relationship()


class Ride(Base):
    __tablename__ = "rides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    ride_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ride_types.id"))
    status: Mapped[RideStatus] = mapped_column(Enum(RideStatus), default=RideStatus.requested, index=True)

    pickup_lat: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    pickup_lng: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    pickup_address: Mapped[str] = mapped_column(Text)
    drop_lat: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    drop_lng: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    drop_address: Mapped[str] = mapped_column(Text)

    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    duration_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    route_polyline: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_fare: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    final_fare: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    surge_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.00"))
    start_otp: Mapped[str | None] = mapped_column(String(6), nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    driver_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    driver_arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ride_type: Mapped["RideType"] = relationship()
    status_events: Mapped[list["RideStatusEvent"]] = relationship(back_populates="ride")


class RideStatusEvent(Base):
    __tablename__ = "ride_status_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ride_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rides.id"), index=True)
    status: Mapped[RideStatus] = mapped_column(Enum(RideStatus))
    message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ride: Mapped["Ride"] = relationship(back_populates="status_events")
