# tests/test_db_models.py

"""Tests for the database models."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rankforge.db.models import Player


@pytest.mark.asyncio
async def test_create_player(db_session: AsyncSession):
    """Test creating a Player instance in the database."""
    # 1. Create a new player object
    new_player = Player(name="TestPlayer")

    # 2. Add it to the session and commit
    db_session.add(new_player)
    await db_session.commit()
    await db_session.refresh(new_player)

    # 3. Assert that the player has been given an ID
    assert new_player.id is not None
    assert new_player.name == "TestPlayer"

    # 4. Query the database to confirm it was saved
    result = await db_session.execute(select(Player).where(Player.name == "TestPlayer"))
    player_from_db = result.scalar_one_or_none()

    assert player_from_db is not None
    assert player_from_db.id == new_player.id
    assert player_from_db.name == "TestPlayer"
