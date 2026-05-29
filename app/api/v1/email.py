from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.email import EmailVerificationSentData, EmailVerifyRequest
from app.schemas.response import ApiResponse, ok
from app.services import email_service

router = APIRouter(prefix="/email", tags=["email"])


@router.post("/send-verification", response_model=ApiResponse[EmailVerificationSentData])
async def send_verification(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Send a verification code to the rider's email (`debug_code` when in dev)."""

    debug_code = await email_service.send_verification(db, rider)
    return ok(
        EmailVerificationSentData(debug_code=debug_code),
        message="Verification code sent",
    )


@router.post("/verify", response_model=ApiResponse[None])
async def verify_email(
    body: EmailVerifyRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Verify email and grant one-time wallet credit bonus."""

    await email_service.verify_email(db, rider, body.code)
    return ok(message="Email verified")
