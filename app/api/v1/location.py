from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.location import ReverseGeocodeResponse
from app.services import geo_service

router = APIRouter(prefix="/location", tags=["location"])


@router.get("/reverse-geocode", response_model=ReverseGeocodeResponse)
async def reverse_geocode(
    lat: Annotated[Decimal, Query(ge=-90, le=90)],
    lng: Annotated[Decimal, Query(ge=-180, le=180)],
):
    address = await geo_service.reverse_geocode(lat, lng)
    return ReverseGeocodeResponse(lat=lat, lng=lng, formatted_address=address)
