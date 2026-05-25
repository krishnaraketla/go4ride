from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db
from app.models.user import User
from app.schemas.wallet import WalletResponse
from app.services import wallet_service

router = APIRouter(tags=["wallet"])


@router.get("/wallet", response_model=WalletResponse)
async def get_wallet(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    balance, currency = await wallet_service.get_wallet_balance(db, rider.id)
    return WalletResponse(balance=balance, currency=currency)
