from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.email import EmailVerificationSentResponse, EmailVerifyRequest
from app.services import email_service

router = APIRouter(prefix="/email", tags=["email"])


@router.post("/send-verification", response_model=EmailVerificationSentResponse)
async def send_verification(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Send a verification code to the rider's email (`debug_code` when in dev)."""

    debug_code = await email_service.send_verification(db, rider)
    return EmailVerificationSentResponse(
        message="Verification code sent",
        debug_code=debug_code,
    )


@router.post("/verify")
async def verify_email(
    body: EmailVerifyRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Verify email and grant one-time wallet credit bonus."""

    await email_service.verify_email(db, rider, body.code)
    return {"message": "Email verified"}
