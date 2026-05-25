from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.address import UserSettings
from app.models.user import User
from app.schemas.settings import SettingsResponse, SettingsUpdateRequest


async def get_settings(db: AsyncSession, user: User) -> SettingsResponse:
    row = await _get_or_create(db, user.id)
    return SettingsResponse(
        notifications_enabled=row.notifications_enabled,
        language=row.language,
    )


async def update_settings(
    db: AsyncSession, user: User, data: SettingsUpdateRequest
) -> SettingsResponse:
    row = await _get_or_create(db, user.id)
    if data.notifications_enabled is not None:
        row.notifications_enabled = data.notifications_enabled
    if data.language is not None:
        row.language = data.language
    return SettingsResponse(
        notifications_enabled=row.notifications_enabled,
        language=row.language,
    )


async def _get_or_create(db: AsyncSession, user_id) -> UserSettings:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user_id)
        db.add(row)
        await db.flush()
    return row
