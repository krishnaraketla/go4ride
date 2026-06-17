"""Unit tests for live ride map / WebSocket payload helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.enums import RideStatus
from app.models.ride import Ride
from app.services import ride_live_service


@pytest.mark.asyncio
async def test_build_status_payload_includes_type_and_polyline() -> None:
    ride = Ride(
        id=uuid4(),
        rider_id=uuid4(),
        ride_type_id=uuid4(),
        status=RideStatus.searching_driver,
        pickup_lat=Decimal("12.9716"),
        pickup_lng=Decimal("77.5946"),
        pickup_address="Pickup",
        drop_lat=Decimal("12.9352"),
        drop_lng=Decimal("77.6245"),
        drop_address="Drop",
        estimated_fare=Decimal("120.00"),
        route_polyline="encoded_trip_polyline",
    )
    db = AsyncMock()

    payload = await ride_live_service.build_status_payload(
        db,
        ride,
        RideStatus.searching_driver,
        "Searching for driver",
        datetime.now(timezone.utc),
    )
    assert payload["type"] == "status"
    assert payload["route_polyline"] == "encoded_trip_polyline"
    assert payload["status"] == "searching_driver"


@pytest.mark.asyncio
async def test_publish_location_update_skips_when_throttled() -> None:
    driver_id = uuid4()
    ride_id = uuid4()
    db = AsyncMock()
    fake_ride = type("Ride", (), {"id": ride_id})()

    with (
        patch.object(
            ride_live_service,
            "get_active_ride_for_driver",
            AsyncMock(return_value=fake_ride),
        ),
        patch(
            "app.services.ride_live_service.should_publish_location_update",
            AsyncMock(return_value=False),
        ) as throttle,
        patch(
            "app.services.ride_live_service.build_location_payload",
            AsyncMock(),
        ) as build_payload,
    ):
        await ride_live_service.publish_location_update(db, driver_id)
        throttle.assert_awaited_once()
        build_payload.assert_not_called()


@pytest.mark.asyncio
async def test_get_polylines_for_ride_returns_route_and_cached_leg() -> None:
    ride = Ride(
        id=uuid4(),
        rider_id=uuid4(),
        driver_id=uuid4(),
        ride_type_id=uuid4(),
        status=RideStatus.driver_assigned,
        pickup_lat=Decimal("12.9716"),
        pickup_lng=Decimal("77.5946"),
        pickup_address="Pickup",
        drop_lat=Decimal("12.9352"),
        drop_lng=Decimal("77.6245"),
        drop_address="Drop",
        estimated_fare=Decimal("120.00"),
        route_polyline="encoded_trip_polyline",
    )
    db = AsyncMock()

    with patch(
        "app.services.ride_live_service.get_cached_leg_polyline",
        AsyncMock(return_value="encoded_leg_polyline"),
    ):
        route, leg = await ride_live_service.get_polylines_for_ride(db, ride)

    assert route == "encoded_trip_polyline"
    assert leg == "encoded_leg_polyline"
