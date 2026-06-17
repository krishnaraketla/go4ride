from decimal import Decimal

from pydantic import BaseModel


class DriverTrendPoint(BaseModel):
    label: str
    date: str
    ride_count: int
    earnings: Decimal


class DriverInsightsResponse(BaseModel):
    period: str
    earnings: Decimal
    rides_count: int
    online_hours: float
    active_hours: float
    earnings_per_hour: Decimal | None
    comparison_pct: float | None
    trend: list[DriverTrendPoint]
    currency: str
