from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import forbidden, unauthorized
from app.core.security import verify_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> User:
    if credentials is None:
        raise unauthorized()
    try:
        payload = verify_token(credentials.credentials, "access")
    except ValueError as exc:
        raise unauthorized() from exc
    user_id = UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized("User not found")
    if user.is_blocked:
        raise forbidden("Account is blocked")
    return user


async def get_current_rider(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.rider:
        raise forbidden("Rider access required")
    return user


async def get_current_driver(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.driver:
        raise forbidden("Driver access required")
    return user


def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    return idempotency_key
