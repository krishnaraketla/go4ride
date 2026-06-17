"""Unit tests for driver earnings period helpers (no DB)."""

from datetime import datetime, timezone
from decimal import Decimal

from app.services.driver_earnings_service import (
    build_weekly_trend,
    period_bounds,
)


def test_daily_period_bounds() -> None:
    now = datetime(2026, 6, 17, 15, 30, tzinfo=timezone.utc)
    start, end, prev_start, prev_end = period_bounds("daily", now)
    assert start.day == 17 and start.hour == 0
    assert end == now
    assert (prev_end - prev_start).days == 1


def test_weekly_period_bounds() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    start, end, prev_start, prev_end = period_bounds("weekly", now)
    assert start.weekday() == 0
    assert (end - start).days == 7
    assert (prev_end - prev_start).days == 7


def test_build_weekly_trend_includes_earnings() -> None:
    from datetime import date

    start = datetime(2026, 5, 19, tzinfo=timezone.utc)
    counts = {date(2026, 5, 24): 3}
    earnings = {date(2026, 5, 24): Decimal("284.00")}
    points = build_weekly_trend(start, counts, earnings)
    sat = next(p for p in points if p["label"] == "Sat")
    assert sat["ride_count"] == 3
    assert sat["earnings"] == Decimal("284.00")
