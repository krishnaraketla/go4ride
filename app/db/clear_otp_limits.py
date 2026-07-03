"""Clear OTP rate-limit keys on startup when CLEAR_OTP_LIMITS_ON_STARTUP is enabled."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.seed import MOCK_DRIVER_PHONE


def _default_otp_phones() -> list[str]:
    """Mock driver + OTP-bypass / seed test phones (deduped, stable order)."""
    settings = get_settings()
    phones: list[str] = []
    seen: set[str] = set()
    for phone in (MOCK_DRIVER_PHONE, *settings.otp_bypass_phones, *settings.clear_otp_limits_phones):
        if phone and phone not in seen:
            seen.add(phone)
            phones.append(phone)
    return phones


def _otp_rate_limit_keys(phones: list[str]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for phone in phones:
        stripped = phone.lstrip("+")
        for variant in (phone, stripped, f"+{stripped}"):
            key = f"otp:{variant}"
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


async def clear_otp_limits(phones: list[str] | None = None) -> int:
    """Delete Redis OTP rate-limit keys for the given phone numbers."""
    client = await get_redis()
    keys = _otp_rate_limit_keys(phones if phones is not None else _default_otp_phones())
    if not keys:
        return 0
    deleted = await client.delete(*keys)
    return int(deleted)


async def clear_otp_limits_on_startup_if_enabled() -> None:
    settings = get_settings()
    if not settings.clear_otp_limits_on_startup:
        print("CLEAR_OTP_LIMITS_ON_STARTUP disabled; skipping OTP rate-limit cleanup")
        return
    phones = settings.clear_otp_limits_phones or _default_otp_phones()
    deleted = await clear_otp_limits(phones)
    print(f"Cleared {deleted} OTP rate-limit key(s) for: {', '.join(phones)}")


def main() -> None:
    asyncio.run(clear_otp_limits_on_startup_if_enabled())


if __name__ == "__main__":
    main()
