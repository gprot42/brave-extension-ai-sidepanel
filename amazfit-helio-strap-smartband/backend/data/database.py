"""Database setup and session management."""

import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.config import DATABASE_URL
from backend.data.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(DATABASE_URL, echo=False,
                             connect_args={"timeout": 30})
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables if they don't exist, then clean up corrupt data."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Enable WAL mode so reads don't block on writes (and vice versa)
        await conn.execute(text("PRAGMA journal_mode=WAL"))

    # Clean up corrupt/duplicate data on startup
    try:
        async with async_session() as session:
            # Remove corrupt HR readings (calibration, out-of-range)
            r1 = await session.execute(
                text("DELETE FROM heart_rate WHERE bpm < 30 OR bpm > 220 OR bpm = 128")
            )
            # Remove duplicate HR entries (keep earliest id per timestamp)
            r2 = await session.execute(
                text("DELETE FROM heart_rate WHERE id NOT IN "
                     "(SELECT MIN(id) FROM heart_rate GROUP BY timestamp)")
            )
            # Remove future-dated stress/HRV entries
            r3 = await session.execute(
                text("DELETE FROM stress WHERE timestamp > datetime('now', '+1 hour')")
            )
            r4 = await session.execute(
                text("DELETE FROM hrv WHERE timestamp > datetime('now', '+1 hour')")
            )
            await session.commit()
            total = r1.rowcount + r2.rowcount + r3.rowcount + r4.rowcount
            if total > 0:
                logger.info("DB cleanup: removed %d corrupt/duplicate/future entries "
                            "(HR: %d invalid + %d dupes, Stress: %d future, HRV: %d future)",
                            total, r1.rowcount, r2.rowcount, r3.rowcount, r4.rowcount)
    except Exception as e:
        logger.warning("DB cleanup failed (non-fatal): %s", e)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
