from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.ride import DriverSummary


class InvoiceResponse(BaseModel):
    available: bool
    ride_id: UUID | None = None
    status: str | None = None
    pickup_address: str | None = None
    drop_address: str | None = None
    final_fare: Decimal | None = None
    currency: str | None = None
    completed_at: datetime | None = None
    driver: DriverSummary | None = None
    download_url: str | None = None
