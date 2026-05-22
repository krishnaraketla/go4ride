import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


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

    user: Mapped["User"] = relationship()  # type: ignore[name-defined]
