# tests/test_transaction_rollback.py

"""Tests for transaction atomicity and rollback behavior."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rankforge.db.models import GameProfile, Match, MatchParticipant
from rankforge.exceptions import RatingCalculationError

# =============================================================================
# Helper Functions
# =============================================================================


async def create_game(client: AsyncClient, name: str) -> int:
    """Helper to create a game and return its ID."""
    res = await client.post(
        "/games/", json={"name": name, "rating_strategy": "glicko2"}
    )
    assert res.status_code == 201
    return int(res.json()["id"])


async def create_player(client: AsyncClient, name: str) -> int:
    """Helper to create a player and return its ID."""
    res = await client.post("/players/", json={"name": name})
    assert res.status_code == 201
    return int(res.json()["id"])


async def count_matches(db: AsyncSession) -> int:
    """Count total matches in database."""
    result = await db.execute(select(Match))
    return len(list(result.scalars().all()))


async def count_game_profiles(db: AsyncSession, game_id: int) -> int:
    """Count game profiles for a specific game."""
    result = await db.execute(select(GameProfile).where(GameProfile.game_id == game_id))
    return len(list(result.scalars().all()))


async def count_match_participants(db: AsyncSession) -> int:
    """Count total match participants in database."""
    result = await db.execute(select(MatchParticipant))
    return len(list(result.scalars().all()))


# =============================================================================
# Transaction Rollback Tests
# =============================================================================


@pytest.mark.asyncio
async def test_match_rollback_on_rating_engine_failure(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that match creation is rolled back if rating engine fails."""
    # 1. ARRANGE: Create game and players.
    game_id = await create_game(async_client, "RollbackTestGame1")
    player1_id = await create_player(async_client, "RollbackPlayer1")
    player2_id = await create_player(async_client, "RollbackPlayer2")

    # Count initial matches
    initial_match_count = await count_matches(db_session)

    # 2. ACT: Try to create a match with a mocked rating engine failure.
    match_payload = {
        "game_id": game_id,
        "participants": [
            {"player_id": player1_id, "team_id": 1, "outcome": {"result": "win"}},
            {"player_id": player2_id, "team_id": 2, "outcome": {"result": "loss"}},
        ],
    }

    with patch(
        "rankforge.rating.glicko2_engine.update_ratings_for_match",
        side_effect=RatingCalculationError("Simulated rating failure"),
    ):
        response = await async_client.post("/matches/", json=match_payload)

    # 3. ASSERT: Request should fail with 500.
    assert response.status_code == 500

    # Match count should be unchanged (rollback worked)
    final_match_count = await count_matches(db_session)
    assert final_match_count == initial_match_count


@pytest.mark.asyncio
async def test_game_profiles_not_created_on_match_failure(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that GameProfiles are not created when match creation fails."""
    # 1. ARRANGE: Create a new game and new players.
    game_id = await create_game(async_client, "ProfileRollbackGame")
    player1_id = await create_player(async_client, "ProfileRollbackP1")
    player2_id = await create_player(async_client, "ProfileRollbackP2")

    # Initial profile count for this game should be 0
    initial_profiles = await count_game_profiles(db_session, game_id)
    assert initial_profiles == 0

    # 2. ACT: Try to create a match with a mocked failure.
    match_payload = {
        "game_id": game_id,
        "participants": [
            {"player_id": player1_id, "team_id": 1, "outcome": {"result": "win"}},
            {"player_id": player2_id, "team_id": 2, "outcome": {"result": "loss"}},
        ],
    }

    with patch(
        "rankforge.rating.glicko2_engine.update_ratings_for_match",
        side_effect=RatingCalculationError("Simulated profile failure"),
    ):
        response = await async_client.post("/matches/", json=match_payload)

    # 3. ASSERT: Request should fail with 500.
    assert response.status_code == 500

    # Profile count should still be 0 (profiles were rolled back)
    final_profiles = await count_game_profiles(db_session, game_id)
    assert final_profiles == 0


@pytest.mark.asyncio
async def test_participants_not_created_on_match_failure(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that MatchParticipants are not created when match creation fails."""
    # 1. ARRANGE: Create game and players.
    game_id = await create_game(async_client, "ParticipantRollbackGame")
    player1_id = await create_player(async_client, "ParticipantRollbackP1")
    player2_id = await create_player(async_client, "ParticipantRollbackP2")

    # Initial participant count
    initial_participants = await count_match_participants(db_session)

    # 2. ACT: Try to create a match with a mocked failure after participant creation.
    match_payload = {
        "game_id": game_id,
        "participants": [
            {"player_id": player1_id, "team_id": 1, "outcome": {"result": "win"}},
            {"player_id": player2_id, "team_id": 2, "outcome": {"result": "loss"}},
        ],
    }

    with patch(
        "rankforge.rating.glicko2_engine.update_ratings_for_match",
        side_effect=RatingCalculationError("Failure after participants"),
    ):
        response = await async_client.post("/matches/", json=match_payload)

    # 3. ASSERT: Request should fail.
    assert response.status_code == 500

    # Participant count should be unchanged (rollback worked)
    final_participants = await count_match_participants(db_session)
    assert final_participants == initial_participants


@pytest.mark.asyncio
async def test_successful_match_creates_all_data(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that successful match creation persists all related data."""
    # 1. ARRANGE: Create a new game and new players.
    game_id = await create_game(async_client, "SuccessfulMatchGame")
    player1_id = await create_player(async_client, "SuccessP1")
    player2_id = await create_player(async_client, "SuccessP2")

    # Initial counts
    initial_matches = await count_matches(db_session)
    initial_profiles = await count_game_profiles(db_session, game_id)
    initial_participants = await count_match_participants(db_session)

    # 2. ACT: Create a match successfully.
    match_payload = {
        "game_id": game_id,
        "participants": [
            {"player_id": player1_id, "team_id": 1, "outcome": {"result": "win"}},
            {"player_id": player2_id, "team_id": 2, "outcome": {"result": "loss"}},
        ],
    }
    response = await async_client.post("/matches/", json=match_payload)

    # 3. ASSERT: Request should succeed.
    assert response.status_code == 201

    # All data should be created
    final_matches = await count_matches(db_session)
    final_profiles = await count_game_profiles(db_session, game_id)
    final_participants = await count_match_participants(db_session)

    # 1 new match
    assert final_matches == initial_matches + 1
    # 2 new profiles (one per player)
    assert final_profiles == initial_profiles + 2
    # 2 new participants
    assert final_participants == initial_participants + 2


@pytest.mark.asyncio
async def test_validation_error_before_database_changes(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that validation errors prevent any database changes."""
    # 1. ARRANGE: Create a game and only one player.
    game_id = await create_game(async_client, "ValidationErrorGame")
    player_id = await create_player(async_client, "ValidationP1")

    # Initial counts
    initial_matches = await count_matches(db_session)

    # 2. ACT: Try to create a match with only one participant (validation error).
    match_payload = {
        "game_id": game_id,
        "participants": [
            {"player_id": player_id, "team_id": 1, "outcome": {"result": "win"}},
        ],
    }
    response = await async_client.post("/matches/", json=match_payload)

    # 3. ASSERT: Request should fail with validation error.
    assert response.status_code == 422

    # No database changes
    final_matches = await count_matches(db_session)
    assert final_matches == initial_matches


@pytest.mark.asyncio
async def test_nonexistent_player_error_before_database_changes(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that nonexistent player error prevents any database changes."""
    # 1. ARRANGE: Create a game and only one player.
    game_id = await create_game(async_client, "NonexistentPlayerGame")
    player_id = await create_player(async_client, "ExistingPlayer")

    # Initial counts
    initial_matches = await count_matches(db_session)
    initial_profiles = await count_game_profiles(db_session, game_id)

    # 2. ACT: Try to create a match with a nonexistent player.
    match_payload = {
        "game_id": game_id,
        "participants": [
            {"player_id": player_id, "team_id": 1, "outcome": {"result": "win"}},
            {"player_id": 999999, "team_id": 2, "outcome": {"result": "loss"}},
        ],
    }
    response = await async_client.post("/matches/", json=match_payload)

    # 3. ASSERT: Request should fail with 404.
    assert response.status_code == 404

    # No database changes
    final_matches = await count_matches(db_session)
    final_profiles = await count_game_profiles(db_session, game_id)
    assert final_matches == initial_matches
    # The existing player's profile should NOT be created either
    assert final_profiles == initial_profiles


@pytest.mark.asyncio
async def test_nonexistent_game_error_before_database_changes(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that nonexistent game error prevents any database changes."""
    # 1. ARRANGE: Create players only.
    player1_id = await create_player(async_client, "NoGameP1")
    player2_id = await create_player(async_client, "NoGameP2")

    # Initial counts
    initial_matches = await count_matches(db_session)

    # 2. ACT: Try to create a match for a nonexistent game.
    match_payload = {
        "game_id": 999999,
        "participants": [
            {"player_id": player1_id, "team_id": 1, "outcome": {"result": "win"}},
            {"player_id": player2_id, "team_id": 2, "outcome": {"result": "loss"}},
        ],
    }
    response = await async_client.post("/matches/", json=match_payload)

    # 3. ASSERT: Request should fail with 404.
    assert response.status_code == 404

    # No database changes
    final_matches = await count_matches(db_session)
    assert final_matches == initial_matches
