"""Driver online session tracking."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver_session import DriverOnlineSession


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def open_session(db: AsyncSession, driver_id: UUID) -> DriverOnlineSession:
    """Start a new online session if none is open."""
    existing = await _get_open_session(db, driver_id)
    if existing is not None:
        return existing
    session = DriverOnlineSession(driver_id=driver_id, started_at=_utc_now())
    db.add(session)
    await db.flush()
    return session


async def close_session(db: AsyncSession, driver_id: UUID) -> None:
    """Close the driver's open online session, if any."""
    session = await _get_open_session(db, driver_id)
    if session is None:
        return
    session.ended_at = _utc_now()
    await db.flush()


async def _get_open_session(db: AsyncSession, driver_id: UUID) -> DriverOnlineSession | None:
    result = await db.execute(
        select(DriverOnlineSession)
        .where(DriverOnlineSession.driver_id == driver_id, DriverOnlineSession.ended_at.is_(None))
        .order_by(DriverOnlineSession.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
