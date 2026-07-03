from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Coordinates(BaseModel):
    lat: Decimal = Field(..., ge=-90, le=90)
    lng: Decimal = Field(..., ge=-180, le=180)


class RideQuoteRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "pickup": {"lat": "37.7749", "lng": "-122.4194"},
                    "drop": {"lat": "37.7599", "lng": "-122.4148"},
                }
            ]
        },
    )

    pickup: Coordinates
    drop: Coordinates


class RouteSummary(BaseModel):
    distance_km: Decimal
    duration_min: Decimal
    polyline: str | None = None


class RideQuoteOption(BaseModel):
    slug: str
    name: str
    description: str | None = None
    icon_url: str | None = None
    available: bool
    drivers_nearby: int
    estimated_fare: Decimal
    pickup_eta_min: int | None = None
    trip_duration_min: int
    total_eta_min: int | None = None


class RideQuoteResponse(BaseModel):
    pickup_address: str
    drop_address: str
    route: RouteSummary
    currency: str
    surge_multiplier: Decimal
    quote_expires_at: datetime
    options: list[RideQuoteOption]


class CreateRideRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "pickup": {"lat": "37.7749", "lng": "-122.4194"},
                    "drop": {"lat": "37.7599", "lng": "-122.4148"},
                    "ride_type_slug": "mini",
                }
            ]
        },
    )

    pickup: Coordinates
    drop: Coordinates
    pickup_address: str | None = None
    drop_address: str | None = None
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
    route_polyline: str | None = None
    invoice_available: bool = False
    start_otp: str | None = None


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
    route_polyline: str | None = None
    leg_polyline: str | None = None
    start_otp: str | None = None


class RideHistoryResponse(BaseModel):
    items: list[RideResponse]
    page: int
    limit: int
    total: int
