import pytest

from app.db import clear_otp_limits as clear_otp_limits_module


def test_otp_rate_limit_keys_includes_plus_variants() -> None:
    keys = clear_otp_limits_module._otp_rate_limit_keys(["+919999000001"])
    assert keys == ["otp:+919999000001", "otp:919999000001"]


@pytest.mark.asyncio
async def test_clear_otp_limits_skipped_when_flag_disabled(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setenv("CLEAR_OTP_LIMITS_ON_STARTUP", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    called = False

    async def fake_clear_otp_limits(phones: list[str] | None = None) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(clear_otp_limits_module, "clear_otp_limits", fake_clear_otp_limits)
    await clear_otp_limits_module.clear_otp_limits_on_startup_if_enabled()

    assert not called
    assert "skipping OTP rate-limit cleanup" in capsys.readouterr().out
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_clear_otp_limits_runs_when_flag_enabled(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setenv("CLEAR_OTP_LIMITS_ON_STARTUP", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    async def fake_clear_otp_limits(phones: list[str] | None = None) -> int:
        assert phones == ["+919999000001"]
        return 2

    monkeypatch.setattr(clear_otp_limits_module, "clear_otp_limits", fake_clear_otp_limits)
    await clear_otp_limits_module.clear_otp_limits_on_startup_if_enabled()

    out = capsys.readouterr().out
    assert "Cleared 2 OTP rate-limit key(s)" in out
    assert "+919999000001" in out
    get_settings.cache_clear()
