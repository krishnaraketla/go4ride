"""Unit tests for insights period bounds (no DB)."""

from datetime import datetime, timezone

from app.services.insights_service import _period_bounds


def test_weekly_period_bounds() -> None:
    # Wednesday 2026-05-20
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    start, end, prev_start, prev_end = _period_bounds("weekly", now)
    assert start.weekday() == 0  # Monday
    assert (end - start).days == 7
    assert (prev_end - prev_start).days == 7


def test_monthly_period_bounds() -> None:
    now = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    start, end, prev_start, prev_end = _period_bounds("monthly", now)
    assert start.month == 5 and start.day == 1
    assert end.month == 6 and end.day == 1
    assert prev_start.month == 4
