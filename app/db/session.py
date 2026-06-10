import logging
import time
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    echo=settings.sqlalchemy_echo,
    pool_pre_ping=True,
)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

if settings.db_slow_query_ms > 0:

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        start_times = conn.info.get("query_start_time")
        if not start_times:
            return
        elapsed_ms = (time.perf_counter() - start_times.pop()) * 1000
        if elapsed_ms >= settings.db_slow_query_ms:
            sql = statement if isinstance(statement, str) else str(statement)
            if len(sql) > 200:
                sql = sql[:200] + "..."
            logger.warning(
                "slow_query",
                extra={"duration_ms": round(elapsed_ms, 2), "sql": sql},
            )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(
                "database_session_rollback",
                extra={"exception_type": type(exc).__name__},
            )
            raise


async def check_postgres() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        logger.exception("postgres_check_failed")
        return False
