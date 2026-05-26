from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Coordinates(BaseModel):
    lat: Decimal = Field(..., ge=-90, le=90)
    lng: Decimal = Field(..., ge=-180, le=180)


class RideEstimateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "pickup": {"lat": "12.9716", "lng": "77.5946"},
                    "drop": {"lat": "12.9352", "lng": "77.6245"},
                    "ride_type_slug": "mini",
                }
            ]
        },
    )

    pickup: Coordinates
    drop: Coordinates
    ride_type_slug: str = Field(..., examples=["mini", "sedan", "bike", "xl"])


class RideEstimateResponse(BaseModel):
    distance_km: Decimal
    duration_min: Decimal
    estimated_fare: Decimal
    currency: str
    surge_multiplier: Decimal


class RideTypeResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    icon_url: str | None

    model_config = {"from_attributes": True}


class CreateRideRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "pickup": {"lat": "12.9716", "lng": "77.5946"},
                    "drop": {"lat": "12.9352", "lng": "77.6245"},
                    "pickup_address": "MG Road, Bengaluru",
                    "drop_address": "Koramangala, Bengaluru",
                    "ride_type_slug": "mini",
                }
            ]
        },
    )

    pickup: Coordinates
    drop: Coordinates
    pickup_address: str
    drop_address: str
    ride_type_slug: str


class DriverSummary(BaseModel):
    id: UUID
    name: str
    phone: str
    vehicle_model: str
    vehicle_plate: str
    vehicle_color: str
    lat: Decimal | None = None
    lng: Decimal | None = None
    eta_min: int | None = None


class RideResponse(BaseModel):
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
    ride_type_slug: str | None = None
    requested_at: datetime
    driver_assigned_at: datetime | None = None
    driver_arrived_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    driver: DriverSummary | None = None
    invoice_available: bool = False


class RepeatRideResponse(BaseModel):
    pickup: Coordinates
    drop: Coordinates
    pickup_address: str
    drop_address: str
    ride_type_slug: str


class RideStatusResponse(BaseModel):
    id: UUID
    status: str
    message: str | None = None
    driver: DriverSummary | None = None


class RideHistoryResponse(BaseModel):
    items: list[RideResponse]
    page: int
    limit: int
    total: int
