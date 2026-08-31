import time
from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from backend.app.config import settings
from backend.app.models.db import Base
from backend.app.observability.logging import get_logger

logger = get_logger("rebutio.db")

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30.0

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    future=True,
)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
        except Exception:
            pass

# Slow query listener via synchronous engine
@event.listens_for(engine.sync_engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.perf_counter()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start_time = getattr(context, "_query_start_time", None)
    if start_time:
        duration_ms = (time.perf_counter() - start_time) * 1000
        slow_threshold_ms = getattr(settings, "DB_SLOW_QUERY_MS", 500)
        if duration_ms > slow_threshold_ms:
            # Extract safe statement prefix without parameters
            stmt_prefix = statement.strip()[:100].replace("\n", " ")
            logger.warning(
                "db.operation.slow",
                statement_prefix=stmt_prefix,
                duration_ms=round(duration_ms, 2),
                threshold_ms=slow_threshold_ms,
            )


async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as e:
            logger.error("db.transaction.failed", exception_type=e.__class__.__name__)
            await session.rollback()
            raise
        finally:
            await session.close()
