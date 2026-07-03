"""Unit tests for rider-visible trip start OTP."""

from decimal import Decimal
from uuid import uuid4

from app.models.enums import RideStatus
from app.models.ride import Ride
from app.services.ride_live_service import rider_visible_start_otp


def _ride(status: RideStatus, start_otp: str | None = None) -> Ride:
    return Ride(
        id=uuid4(),
        rider_id=uuid4(),
        status=status,
        pickup_lat=Decimal("37.7749"),
        pickup_lng=Decimal("-122.4194"),
        pickup_address="Pickup",
        drop_lat=Decimal("37.7599"),
        drop_lng=Decimal("-122.4148"),
        drop_address="Drop",
        estimated_fare=Decimal("100"),
        surge_multiplier=Decimal("1"),
        start_otp=start_otp,
    )


def test_start_otp_visible_only_when_driver_arrived() -> None:
    assert rider_visible_start_otp(_ride(RideStatus.driver_arrived, "482910")) == "482910"
    assert rider_visible_start_otp(_ride(RideStatus.driver_assigned, "482910")) is None
    assert rider_visible_start_otp(_ride(RideStatus.in_progress, "482910")) is None
    assert rider_visible_start_otp(_ride(RideStatus.driver_arrived, None)) is None
