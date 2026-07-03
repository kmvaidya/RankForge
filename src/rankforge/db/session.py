# src/rankforge/db/session.py

"""Database session management."""

import logging
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# Database URL from environment variable with SQLite fallback for development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./rankforge.db")


def _create_engine():
    """Create the async engine with appropriate configuration.

    SQLite doesn't support connection pooling, so we only configure
    pool settings for other databases like PostgreSQL.
    """
    url = DATABASE_URL

    # SQLite doesn't support connection pooling
    if url.startswith("sqlite"):
        return create_async_engine(
            url,
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
        )

    # PostgreSQL and other databases get full pool configuration
    return create_async_engine(
        url,
        pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
    )


# The engine is the core interface to the database.
engine = _create_engine()

# Create a configured "Session" class.
# autocommit=False: Transactions are committed manually.
# autoflush=False: Changes are not flushed to the database until explicitly committed.
# expire_on_commit=False: Objects remain accessible after commit.
AsyncSessionLocal = async_sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session.

    Automatically handles rollback on exceptions and ensures
    the session is properly closed.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error, rolling back: {e}")
            await session.rollback()
            raise
