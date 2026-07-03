# tests/conftest.py

"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from rankforge.db.models import Base
from rankforge.db.session import get_db
from rankforge.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL)
AsyncTestingSessionLocal = async_sessionmaker(
    bind=engine, expire_on_commit=False, autocommit=False, autoflush=False
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for our test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Fixture to create and tear down the test database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Fixture to provide a transactional database session to a test.
    The transaction is rolled back after the test, ensuring isolation.
    """
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncTestingSessionLocal(bind=connection)

    yield session

    # After the test is done, roll back the transaction to clean up.
    await session.close()
    if transaction.is_active:
        await transaction.rollback()
    await connection.close()


@pytest.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Fixture to provide an async test client for the API."""

    # Override the get_db dependency to use the test database
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up the override after the test
    del app.dependency_overrides[get_db]
