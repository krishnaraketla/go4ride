import pytest

from app.db import clear_rides as clear_rides_module


@pytest.mark.asyncio
async def test_clear_rides_skipped_when_flag_disabled(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("CLEAR_RIDES_ON_STARTUP", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    called = False

    async def fake_clear_rides() -> tuple[int, int, int]:
        nonlocal called
        called = True
        return (0, 0, 0)

    monkeypatch.setattr(clear_rides_module, "clear_rides", fake_clear_rides)
    await clear_rides_module.clear_rides_on_startup_if_enabled()

    assert not called
    assert "skipping ride cleanup" in capsys.readouterr().out
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_clear_rides_runs_when_flag_enabled(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("CLEAR_RIDES_ON_STARTUP", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    async def fake_clear_rides() -> tuple[int, int, int]:
        return (3, 2, 1)

    monkeypatch.setattr(clear_rides_module, "clear_rides", fake_clear_rides)
    await clear_rides_module.clear_rides_on_startup_if_enabled()

    out = capsys.readouterr().out
    assert "Cleared 2 ride(s), 3 status event(s)" in out
    assert "reset 1 driver(s)" in out
    get_settings.cache_clear()
