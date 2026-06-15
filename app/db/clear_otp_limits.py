"""Clear OTP rate-limit keys on startup when CLEAR_OTP_LIMITS_ON_STARTUP is enabled."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.seed import MOCK_DRIVER_PHONE

DEFAULT_DEMO_OTP_PHONES = (MOCK_DRIVER_PHONE,)


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
    keys = _otp_rate_limit_keys(phones or list(DEFAULT_DEMO_OTP_PHONES))
    if not keys:
        return 0
    deleted = await client.delete(*keys)
    return int(deleted)


async def clear_otp_limits_on_startup_if_enabled() -> None:
    settings = get_settings()
    if not settings.clear_otp_limits_on_startup:
        print("CLEAR_OTP_LIMITS_ON_STARTUP disabled; skipping OTP rate-limit cleanup")
        return
    deleted = await clear_otp_limits(settings.clear_otp_limits_phones)
    phones = ", ".join(settings.clear_otp_limits_phones)
    print(f"Cleared {deleted} OTP rate-limit key(s) for: {phones}")


def main() -> None:
    asyncio.run(clear_otp_limits_on_startup_if_enabled())


if __name__ == "__main__":
    main()
