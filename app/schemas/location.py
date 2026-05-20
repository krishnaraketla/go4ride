from decimal import Decimal

from pydantic import BaseModel, Field


class ReverseGeocodeResponse(BaseModel):
    lat: Decimal
    lng: Decimal
    formatted_address: str
