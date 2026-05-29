from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.location import ReverseGeocodeResponse
from app.schemas.response import ApiResponse, ok
from app.services import geo_service

router = APIRouter(prefix="/location", tags=["location"])


@router.get("/reverse-geocode", response_model=ApiResponse[ReverseGeocodeResponse])
async def reverse_geocode(
    lat: Annotated[Decimal, Query(ge=-90, le=90)],
    lng: Annotated[Decimal, Query(ge=-180, le=180)],
):
    """Resolve coordinates to a formatted address string."""

    address = await geo_service.reverse_geocode(lat, lng)
    return ok(
        ReverseGeocodeResponse(lat=lat, lng=lng, formatted_address=address),
        message="Address resolved",
    )
