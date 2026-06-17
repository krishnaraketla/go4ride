import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DriverRideActionType


class DriverRideAction(Base):
    __tablename__ = "driver_ride_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rides.id"), index=True
    )
    action: Mapped[DriverRideActionType] = mapped_column(Enum(DriverRideActionType))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
