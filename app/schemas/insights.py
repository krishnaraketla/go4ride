from decimal import Decimal

from pydantic import BaseModel


class TrendPoint(BaseModel):
    label: str
    date: str
    ride_count: int


class DistributionItem(BaseModel):
    slug: str
    name: str
    count: int
    percent: float


class InsightsResponse(BaseModel):
    period: str
    rides_count: int
    total_km: Decimal
    total_spend: Decimal
    currency: str
    trend: list[TrendPoint]
    comparison_pct: float | None
    distribution: list[DistributionItem]
