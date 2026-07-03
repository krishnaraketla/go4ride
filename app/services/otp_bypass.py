"""Fixed-code OTP bypass for pre-seeded test phone numbers."""

from app.core.config import get_settings


def is_otp_bypass_phone(phone: str) -> bool:
    """Return True if ``phone`` is on the OTP bypass allowlist."""
    return phone in get_settings().otp_bypass_phones


def is_otp_bypass(phone: str, code: str | None = None) -> bool:
    """Return True if ``phone`` may skip real OTP verification.

    When ``code`` is omitted, only the phone allowlist is checked (request-otp).
    When ``code`` is provided, it must also match ``otp_bypass_code`` (verify-otp).
    """
    settings = get_settings()
    if phone not in settings.otp_bypass_phones:
        return False
    if code is None:
        return True
    return code == settings.otp_bypass_code
