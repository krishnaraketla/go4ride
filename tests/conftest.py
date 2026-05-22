import os

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_driver_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_DRIVER_ENABLED", "true")
    monkeypatch.setenv("MOCK_DRIVER_AUTO_ADVANCE", "true")
    monkeypatch.setenv("MOCK_DRIVER_ASSIGN_DELAY_SEC", "1")
    monkeypatch.setenv("MOCK_DRIVER_STEP_DELAY_SEC", "1")
    monkeypatch.setenv("OTP_DEBUG", "true")
    get_settings.cache_clear()
