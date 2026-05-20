import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def send_otp_sms(phone: str, code: str) -> None:
    settings = get_settings()
    if settings.otp_provider == "console":
        logger.info("OTP for %s: %s", phone, code)
        return
    if settings.otp_provider == "twilio":
        await _send_twilio(phone, code)
    elif settings.otp_provider == "msg91":
        await _send_msg91(phone, code)


async def _send_twilio(phone: str, code: str) -> None:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            data={
                "From": settings.twilio_from_number,
                "To": phone,
                "Body": f"Your Go4Ride OTP is {code}",
            },
        )


async def _send_msg91(phone: str, code: str) -> None:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://control.msg91.com/api/v5/flow/",
            headers={"authkey": settings.msg91_auth_key},
            json={
                "template_id": settings.msg91_template_id,
                "recipients": [{"mobiles": phone, "OTP": code}],
            },
        )
