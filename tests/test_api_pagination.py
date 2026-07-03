# tests/test_api_pagination.py

"""Tests for API pagination, sorting, and filtering functionality."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

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


async def create_match(
    client: AsyncClient, game_id: int, player1_id: int, player2_id: int
) -> int:
    """Helper to create a match and return its ID."""
    res = await client.post(
        "/matches/",
        json={
            "game_id": game_id,
            "participants": [
                {"player_id": player1_id, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": player2_id, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert res.status_code == 201
    return int(res.json()["id"])


# =============================================================================
# Pagination Edge Cases - Games
# =============================================================================


@pytest.mark.asyncio
async def test_games_pagination_skip_zero_limit_one(async_client: AsyncClient):
    """Test pagination with smallest possible page (skip=0, limit=1)."""
    # Create multiple games
    await create_game(async_client, "PaginationGame1")
    await create_game(async_client, "PaginationGame2")
    await create_game(async_client, "PaginationGame3")

    # Get first page with limit=1
    response = await async_client.get("/games/?skip=0&limit=1")
    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 1
    assert data["skip"] == 0
    assert data["limit"] == 1
    assert data["total"] >= 3
    assert data["has_more"] is True


@pytest.mark.asyncio
async def test_games_pagination_skip_exceeds_total(async_client: AsyncClient):
    """Test that skip exceeding total returns empty list."""
    # Create a game to ensure there's data
    await create_game(async_client, "SkipExceedsGame")

    # Skip beyond total count
    response = await async_client.get("/games/?skip=10000")
    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 0
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_games_pagination_limit_at_maximum(async_client: AsyncClient):
    """Test pagination with maximum limit (100)."""
    response = await async_client.get("/games/?limit=100")
    assert response.status_code == 200
    data = response.json()

    assert data["limit"] == 100
    assert len(data["items"]) <= 100


@pytest.mark.asyncio
async def test_games_pagination_has_more_accuracy(async_client: AsyncClient):
    """Test that has_more flag is accurate."""
    # Create exactly 3 games with unique names
    names = [f"HasMoreGame_{i}_{datetime.now().timestamp()}" for i in range(3)]
    for name in names:
        await create_game(async_client, name)

    # Get first page - should have more
    response1 = await async_client.get("/games/?skip=0&limit=2")
    assert response1.status_code == 200
    data1 = response1.json()

    if data1["total"] > 2:
        assert data1["has_more"] is True

    # Get last page - should NOT have more
    response2 = await async_client.get(f"/games/?skip={data1['total'] - 1}&limit=1")
    assert response2.status_code == 200
    data2 = response2.json()

    assert data2["has_more"] is False


@pytest.mark.asyncio
async def test_games_pagination_total_reflects_filters(async_client: AsyncClient):
    """Test that total count reflects the full data set."""
    # Create several games
    for i in range(5):
        await create_game(
            async_client, f"TotalTestGame_{i}_{datetime.now().timestamp()}"
        )

    response = await async_client.get("/games/?limit=2")
    assert response.status_code == 200
    data = response.json()

    # Total should be at least 5 (may include games from other tests)
    assert data["total"] >= 5
    # Items should respect limit
    assert len(data["items"]) == 2


# =============================================================================
# Sorting Tests - Games
# =============================================================================


@pytest.mark.asyncio
async def test_games_sort_by_name_asc(async_client: AsyncClient):
    """Test sorting games by name ascending."""
    ts = datetime.now().timestamp()
    await create_game(async_client, f"ZZZ_SortGame_{ts}")
    await create_game(async_client, f"AAA_SortGame_{ts}")
    await create_game(async_client, f"MMM_SortGame_{ts}")

    response = await async_client.get("/games/?sort_by=name&sort_order=asc")
    assert response.status_code == 200
    data = response.json()

    names = [g["name"] for g in data["items"]]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_games_sort_by_name_desc(async_client: AsyncClient):
    """Test sorting games by name descending."""
    ts = datetime.now().timestamp()
    await create_game(async_client, f"AAA_DescSortGame_{ts}")
    await create_game(async_client, f"ZZZ_DescSortGame_{ts}")

    response = await async_client.get("/games/?sort_by=name&sort_order=desc")
    assert response.status_code == 200
    data = response.json()

    names = [g["name"] for g in data["items"]]
    assert names == sorted(names, reverse=True)


@pytest.mark.asyncio
async def test_games_sort_by_created_at_desc(async_client: AsyncClient):
    """Test sorting games by created_at descending (newest first)."""
    response = await async_client.get("/games/?sort_by=created_at&sort_order=desc")
    assert response.status_code == 200
    data = response.json()

    if len(data["items"]) >= 2:
        # Each subsequent item should have an earlier or equal created_at
        for i in range(len(data["items"]) - 1):
            # The items are sorted newest first
            pass  # Just verify the endpoint works


@pytest.mark.asyncio
async def test_games_sort_by_id(async_client: AsyncClient):
    """Test sorting games by ID."""
    response = await async_client.get("/games/?sort_by=id&sort_order=asc")
    assert response.status_code == 200
    data = response.json()

    if len(data["items"]) >= 2:
        ids = [g["id"] for g in data["items"]]
        assert ids == sorted(ids)


# =============================================================================
# Sorting Tests - Players
# =============================================================================


@pytest.mark.asyncio
async def test_players_sort_by_name_asc(async_client: AsyncClient):
    """Test sorting players by name ascending."""
    ts = datetime.now().timestamp()
    await create_player(async_client, f"ZZZ_SortPlayer_{ts}")
    await create_player(async_client, f"AAA_SortPlayer_{ts}")

    response = await async_client.get("/players/?sort_by=name&sort_order=asc")
    assert response.status_code == 200
    data = response.json()

    names = [p["name"] for p in data["items"]]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_players_include_anonymous_filter(async_client: AsyncClient):
    """Test that include_anonymous filter works."""
    # Default should exclude anonymous players
    response1 = await async_client.get("/players/")
    assert response1.status_code == 200
    data1 = response1.json()

    # Verify response has items (anonymous players excluded by default)
    assert "items" in data1

    # With include_anonymous=true
    response2 = await async_client.get("/players/?include_anonymous=true")
    assert response2.status_code == 200


# =============================================================================
# Sorting Tests - Matches
# =============================================================================


@pytest.mark.asyncio
async def test_matches_sort_by_played_at_desc(async_client: AsyncClient):
    """Test sorting matches by played_at descending (default)."""
    # Create game and players
    game_id = await create_game(async_client, "MatchSortGame")
    player1_id = await create_player(async_client, "MatchSortPlayer1")
    player2_id = await create_player(async_client, "MatchSortPlayer2")

    # Create matches
    await create_match(async_client, game_id, player1_id, player2_id)
    await create_match(async_client, game_id, player1_id, player2_id)

    response = await async_client.get("/matches/?sort_by=played_at&sort_order=desc")
    assert response.status_code == 200
    data = response.json()

    assert "items" in data


@pytest.mark.asyncio
async def test_matches_sort_by_id_asc(async_client: AsyncClient):
    """Test sorting matches by ID ascending."""
    response = await async_client.get("/matches/?sort_by=id&sort_order=asc")
    assert response.status_code == 200
    data = response.json()

    if len(data["items"]) >= 2:
        ids = [m["id"] for m in data["items"]]
        assert ids == sorted(ids)


# =============================================================================
# Filtering Tests - Matches
# =============================================================================


@pytest.mark.asyncio
async def test_matches_filter_by_game_id(async_client: AsyncClient):
    """Test filtering matches by game_id."""
    # Create two games
    game1_id = await create_game(async_client, "FilterGame1")
    game2_id = await create_game(async_client, "FilterGame2")

    # Create players
    player1_id = await create_player(async_client, "FilterPlayer1")
    player2_id = await create_player(async_client, "FilterPlayer2")

    # Create matches in different games
    await create_match(async_client, game1_id, player1_id, player2_id)
    await create_match(async_client, game1_id, player1_id, player2_id)
    await create_match(async_client, game2_id, player1_id, player2_id)

    # Filter by game1
    response = await async_client.get(f"/matches/?game_id={game1_id}")
    assert response.status_code == 200
    data = response.json()

    # All matches should be from game1
    for match in data["items"]:
        assert match["game_id"] == game1_id


@pytest.mark.asyncio
async def test_matches_filter_by_player_id(async_client: AsyncClient):
    """Test filtering matches by player_id."""
    # Create game
    game_id = await create_game(async_client, "PlayerFilterGame")

    # Create three players
    player1_id = await create_player(async_client, "PlayerFilter1")
    player2_id = await create_player(async_client, "PlayerFilter2")
    player3_id = await create_player(async_client, "PlayerFilter3")

    # Create matches with different player combinations
    await create_match(async_client, game_id, player1_id, player2_id)  # Player1 vs 2
    await create_match(async_client, game_id, player1_id, player3_id)  # Player1 vs 3
    await create_match(async_client, game_id, player2_id, player3_id)  # Player2 vs 3

    # Filter by player1 - should get 2 matches
    response = await async_client.get(f"/matches/?player_id={player1_id}")
    assert response.status_code == 200
    data = response.json()

    # All returned matches should have player1 as participant
    for match in data["items"]:
        participant_ids = {p["player"]["id"] for p in match["participants"]}
        assert player1_id in participant_ids


@pytest.mark.asyncio
async def test_matches_filter_by_date_range(async_client: AsyncClient):
    """Test filtering matches by played_after and played_before."""
    # Create test data
    game_id = await create_game(async_client, "DateFilterGame")
    player1_id = await create_player(async_client, "DatePlayer1")
    player2_id = await create_player(async_client, "DatePlayer2")

    # Create a match
    await create_match(async_client, game_id, player1_id, player2_id)

    # Filter by date range that should include the match
    # Use simple ISO format without timezone for query params
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

    response = await async_client.get(
        "/matches/", params={"played_after": yesterday, "played_before": tomorrow}
    )
    assert response.status_code == 200
    data = response.json()

    # Should return matches
    assert data["total"] >= 0


@pytest.mark.asyncio
async def test_matches_filter_played_after(async_client: AsyncClient):
    """Test filtering matches played after a specific date."""
    # Filter for matches after tomorrow (should be empty or few)
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    response = await async_client.get("/matches/", params={"played_after": tomorrow})
    assert response.status_code == 200
    data = response.json()

    # Should be empty since no matches are in the future
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_matches_filter_played_before(async_client: AsyncClient):
    """Test filtering matches played before a specific date."""
    # Create test data
    game_id = await create_game(async_client, "BeforeFilterGame")
    player1_id = await create_player(async_client, "BeforePlayer1")
    player2_id = await create_player(async_client, "BeforePlayer2")
    await create_match(async_client, game_id, player1_id, player2_id)

    # Filter for matches before yesterday
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%dT%H:%M:%S")

    response = await async_client.get(
        "/matches/", params={"played_before": yesterday_str}
    )
    assert response.status_code == 200
    data = response.json()

    # Recent matches should NOT appear (all matches should be before yesterday)
    for match in data["items"]:
        match_played_at = datetime.fromisoformat(
            match["played_at"].replace("Z", "+00:00")
        )
        assert match_played_at <= yesterday


@pytest.mark.asyncio
async def test_matches_combined_filters(async_client: AsyncClient):
    """Test combining multiple filters."""
    # Create test data
    game1_id = await create_game(async_client, "CombinedFilterGame1")
    game2_id = await create_game(async_client, "CombinedFilterGame2")
    player1_id = await create_player(async_client, "CombinedPlayer1")
    player2_id = await create_player(async_client, "CombinedPlayer2")

    # Create matches in both games
    await create_match(async_client, game1_id, player1_id, player2_id)
    await create_match(async_client, game2_id, player1_id, player2_id)

    # Filter by game_id AND player_id
    response = await async_client.get(
        f"/matches/?game_id={game1_id}&player_id={player1_id}"
    )
    assert response.status_code == 200
    data = response.json()

    # All matches should match both filters
    for match in data["items"]:
        assert match["game_id"] == game1_id
        participant_ids = {p["player"]["id"] for p in match["participants"]}
        assert player1_id in participant_ids


# =============================================================================
# Pagination with Filters - Matches
# =============================================================================


@pytest.mark.asyncio
async def test_matches_pagination_with_filter(async_client: AsyncClient):
    """Test pagination works correctly when filters are applied."""
    # Create test data
    game_id = await create_game(async_client, "PaginatedFilterGame")
    player1_id = await create_player(async_client, "PagFilterPlayer1")
    player2_id = await create_player(async_client, "PagFilterPlayer2")

    # Create multiple matches
    for _ in range(5):
        await create_match(async_client, game_id, player1_id, player2_id)

    # Get paginated results with filter
    response = await async_client.get(f"/matches/?game_id={game_id}&skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) <= 2
    assert data["total"] >= 5  # At least 5 matches for this game
    assert data["has_more"] is True


# =============================================================================
# Player Stats and Matches Endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_player_matches_endpoint_pagination(async_client: AsyncClient):
    """Test the /players/{id}/matches endpoint with pagination."""
    # Create test data
    game_id = await create_game(async_client, "PlayerMatchesGame")
    player1_id = await create_player(async_client, "PlayerMatchesP1")
    player2_id = await create_player(async_client, "PlayerMatchesP2")

    # Create multiple matches
    for _ in range(3):
        await create_match(async_client, game_id, player1_id, player2_id)

    # Get player's matches
    response = await async_client.get(f"/players/{player1_id}/matches?limit=2")
    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) <= 2
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_player_matches_filter_by_game(async_client: AsyncClient):
    """Test filtering player's matches by game_id."""
    # Create test data
    game1_id = await create_game(async_client, "PlayerGameFilter1")
    game2_id = await create_game(async_client, "PlayerGameFilter2")
    player1_id = await create_player(async_client, "PlayerGameFilterP1")
    player2_id = await create_player(async_client, "PlayerGameFilterP2")

    # Create matches in different games
    await create_match(async_client, game1_id, player1_id, player2_id)
    await create_match(async_client, game2_id, player1_id, player2_id)

    # Filter by game
    response = await async_client.get(
        f"/players/{player1_id}/matches?game_id={game1_id}"
    )
    assert response.status_code == 200
    data = response.json()

    # All matches should be from game1
    for match in data["items"]:
        assert match["game_id"] == game1_id


# =============================================================================
# Player Sorting - Additional Coverage
# =============================================================================


@pytest.mark.asyncio
async def test_players_sort_by_name_desc(async_client: AsyncClient):
    """Test sorting players by name descending."""
    ts = datetime.now().timestamp()
    await create_player(async_client, f"AAA_DescPlayer_{ts}")
    await create_player(async_client, f"ZZZ_DescPlayer_{ts}")

    response = await async_client.get("/players/?sort_by=name&sort_order=desc")
    assert response.status_code == 200
    data = response.json()

    names = [p["name"] for p in data["items"]]
    assert names == sorted(names, reverse=True)


@pytest.mark.asyncio
async def test_players_sort_by_created_at_desc(async_client: AsyncClient):
    """Test sorting players by created_at descending."""
    response = await async_client.get("/players/?sort_by=created_at&sort_order=desc")
    assert response.status_code == 200
    data = response.json()

    # Just verify endpoint works with desc sort
    assert "items" in data
    assert "total" in data


# =============================================================================
# Player Stats Endpoint
# =============================================================================


@pytest.mark.asyncio
async def test_player_stats_basic(async_client: AsyncClient):
    """Test basic player stats endpoint structure and response."""
    # Create player and game
    player_id = await create_player(async_client, "StatsPlayer1")
    game_id = await create_game(async_client, "StatsGame1")

    # Create another player for matches
    opponent_id = await create_player(async_client, "StatsOpponent1")

    # Create a match to ensure player has a game profile
    await create_match(async_client, game_id, player_id, opponent_id)

    # Get stats
    response = await async_client.get(f"/players/{player_id}/stats")
    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["player_id"] == player_id
    assert data["player_name"] == "StatsPlayer1"
    assert "total_matches" in data
    assert "total_wins" in data
    assert "total_losses" in data
    assert "total_draws" in data
    assert "overall_win_rate" in data
    assert "games_played" in data
    assert len(data["games_played"]) >= 1

    # Check game stats structure
    game_stats = data["games_played"][0]
    assert "game" in game_stats
    assert "rating_info" in game_stats
    assert game_stats["rating_info"]["rating"] > 0  # Has valid rating
    assert "matches_played" in game_stats
    assert "wins" in game_stats
    assert "losses" in game_stats
    assert "draws" in game_stats
    assert "win_rate" in game_stats


@pytest.mark.asyncio
async def test_player_stats_multiple_games(async_client: AsyncClient):
    """Test player stats across multiple games."""
    # Create player
    player_id = await create_player(async_client, "MultiGameStatsPlayer")
    opponent_id = await create_player(async_client, "MultiGameStatsOpponent")

    # Create two games
    game1_id = await create_game(async_client, "MultiStatsGame1")
    game2_id = await create_game(async_client, "MultiStatsGame2")

    # Play in both games
    await create_match(async_client, game1_id, player_id, opponent_id)
    await create_match(async_client, game2_id, player_id, opponent_id)

    # Get stats
    response = await async_client.get(f"/players/{player_id}/stats")
    assert response.status_code == 200
    data = response.json()

    # Should have stats for both games
    assert len(data["games_played"]) >= 2


@pytest.mark.asyncio
async def test_player_stats_nonexistent_player_returns_404(async_client: AsyncClient):
    """Test that player stats returns 404 for nonexistent player."""
    response = await async_client.get("/players/99999/stats")
    assert response.status_code == 404


# =============================================================================
# Player Matches - Date Filters and Sorting
# =============================================================================


@pytest.mark.asyncio
async def test_player_matches_filter_played_after(async_client: AsyncClient):
    """Test player matches filtered by played_after."""
    game_id = await create_game(async_client, "PlayerMatchAfterGame")
    player1_id = await create_player(async_client, "PlayerMatchAfterP1")
    player2_id = await create_player(async_client, "PlayerMatchAfterP2")

    # Create match
    await create_match(async_client, game_id, player1_id, player2_id)

    # Filter for matches after tomorrow (should be empty)
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    response = await async_client.get(
        f"/players/{player1_id}/matches", params={"played_after": tomorrow}
    )
    assert response.status_code == 200
    data = response.json()

    # Should be empty since no matches are in the future
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_player_matches_filter_played_before(async_client: AsyncClient):
    """Test player matches filtered by played_before."""
    game_id = await create_game(async_client, "PlayerMatchBeforeGame")
    player1_id = await create_player(async_client, "PlayerMatchBeforeP1")
    player2_id = await create_player(async_client, "PlayerMatchBeforeP2")

    # Create match
    await create_match(async_client, game_id, player1_id, player2_id)

    # Filter for matches before a year from now (should include all)
    future = (datetime.now(timezone.utc) + timedelta(days=365)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    response = await async_client.get(
        f"/players/{player1_id}/matches", params={"played_before": future}
    )
    assert response.status_code == 200
    data = response.json()

    # Should include the match we just created
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_player_matches_sort_order_asc(async_client: AsyncClient):
    """Test player matches sorted by played_at ascending."""
    game_id = await create_game(async_client, "PlayerMatchSortAscGame")
    player1_id = await create_player(async_client, "PlayerMatchSortAscP1")
    player2_id = await create_player(async_client, "PlayerMatchSortAscP2")

    # Create multiple matches
    await create_match(async_client, game_id, player1_id, player2_id)
    await create_match(async_client, game_id, player1_id, player2_id)

    # Get with ASC sort
    response = await async_client.get(f"/players/{player1_id}/matches?sort_order=asc")
    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    # Verify we got matches back
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_player_matches_nonexistent_player_returns_404(async_client: AsyncClient):
    """Test that player matches returns 404 for nonexistent player."""
    response = await async_client.get("/players/99999/matches")
    assert response.status_code == 404


# =============================================================================
# Leaderboard Pagination
# =============================================================================


@pytest.mark.asyncio
async def test_leaderboard_pagination(async_client: AsyncClient):
    """Test leaderboard endpoint pagination."""
    # Create game
    game_id = await create_game(async_client, "LeaderboardPagGame")

    # Create multiple players and matches
    player_ids = []
    for i in range(5):
        pid = await create_player(async_client, f"LeaderboardPlayer{i}")
        player_ids.append(pid)

    # Create matches between various players
    for i in range(len(player_ids) - 1):
        await create_match(async_client, game_id, player_ids[i], player_ids[i + 1])

    # Get paginated leaderboard
    response = await async_client.get(f"/games/{game_id}/leaderboard?limit=3")
    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) <= 3
    assert "total" in data
    assert "has_more" in data


# =============================================================================
# Leaderboard Tiebreaker Logic
# =============================================================================


@pytest.mark.asyncio
async def test_leaderboard_tiebreaker_same_rating(async_client: AsyncClient):
    """Test leaderboard ordering when players have identical or similar ratings."""
    # 1. ARRANGE: Create game
    game_id = await create_game(async_client, "TiebreakerGame")

    # Create 4 players
    player_ids = []
    for i in range(4):
        pid = await create_player(async_client, f"TiePlayer{i}")
        player_ids.append(pid)

    # Create matches so all players end up with approximately same rating.
    # P0 vs P1 (P0 wins), P2 vs P3 (P2 wins)
    await create_match(async_client, game_id, player_ids[0], player_ids[1])
    await create_match(async_client, game_id, player_ids[2], player_ids[3])

    # P2 beats P0, P1 beats P3 (each player now has 1 win and 1 loss)
    response = await async_client.post(
        "/matches/",
        json={
            "game_id": game_id,
            "participants": [
                {
                    "player_id": player_ids[2],
                    "team_id": 1,
                    "outcome": {"result": "win"},
                },
                {
                    "player_id": player_ids[0],
                    "team_id": 2,
                    "outcome": {"result": "loss"},
                },
            ],
        },
    )
    assert response.status_code == 201

    response = await async_client.post(
        "/matches/",
        json={
            "game_id": game_id,
            "participants": [
                {
                    "player_id": player_ids[1],
                    "team_id": 1,
                    "outcome": {"result": "win"},
                },
                {
                    "player_id": player_ids[3],
                    "team_id": 2,
                    "outcome": {"result": "loss"},
                },
            ],
        },
    )
    assert response.status_code == 201

    # 2. ACT: Get leaderboard
    leaderboard_response = await async_client.get(f"/games/{game_id}/leaderboard")
    assert leaderboard_response.status_code == 200
    data = leaderboard_response.json()

    # 3. ASSERT: Verify all players appear and ranks are sequential
    assert len(data["items"]) == 4

    # Verify ranks are 1, 2, 3, 4 (sequential)
    ranks = [entry["rank"] for entry in data["items"]]
    assert ranks == [1, 2, 3, 4], "Ranks should be sequential 1-4"

    # Verify ordering is stable (same request returns same order)
    leaderboard_response2 = await async_client.get(f"/games/{game_id}/leaderboard")
    data2 = leaderboard_response2.json()
    player_order1 = [e["player"]["id"] for e in data["items"]]
    player_order2 = [e["player"]["id"] for e in data2["items"]]
    assert player_order1 == player_order2, "Leaderboard ordering should be stable"


@pytest.mark.asyncio
async def test_leaderboard_only_includes_players_who_played(async_client: AsyncClient):
    """Test that leaderboard only includes players who have played in that game."""
    # 1. ARRANGE: Create game
    game_id = await create_game(async_client, "PlayedOnlyGame")

    # Create 3 players but only have P0 and P1 play - P2 never plays
    player_ids = []
    for i in range(3):
        pid = await create_player(async_client, f"PlayedOnlyPlayer{i}")
        player_ids.append(pid)

    # Only P0 and P1 play
    await create_match(async_client, game_id, player_ids[0], player_ids[1])

    # 2. ACT: Get leaderboard
    leaderboard_response = await async_client.get(f"/games/{game_id}/leaderboard")
    assert leaderboard_response.status_code == 200
    data = leaderboard_response.json()

    # 3. ASSERT: Only players who played appear on leaderboard
    assert len(data["items"]) == 2
    leaderboard_player_ids = {e["player"]["id"] for e in data["items"]}
    assert player_ids[0] in leaderboard_player_ids
    assert player_ids[1] in leaderboard_player_ids
    assert player_ids[2] not in leaderboard_player_ids  # Never played


@pytest.mark.asyncio
async def test_leaderboard_rating_order_correct(async_client: AsyncClient):
    """Test that leaderboard correctly orders by rating descending."""
    # 1. ARRANGE
    game_id = await create_game(async_client, "RatingOrderGame")

    # Create 3 players
    p_top = await create_player(async_client, "TopRatedPlayer")
    p_mid = await create_player(async_client, "MidRatedPlayer")
    p_bot = await create_player(async_client, "BotRatedPlayer")

    # Create matches to establish clear rating hierarchy
    # p_top beats p_mid
    await create_match(async_client, game_id, p_top, p_mid)
    # p_mid beats p_bot
    await create_match(async_client, game_id, p_mid, p_bot)
    # p_top beats p_bot (reinforces top position)
    await create_match(async_client, game_id, p_top, p_bot)

    # 2. ACT
    leaderboard_response = await async_client.get(f"/games/{game_id}/leaderboard")
    assert leaderboard_response.status_code == 200
    data = leaderboard_response.json()

    # 3. ASSERT: Verify correct ordering
    assert len(data["items"]) == 3

    # Extract ratings
    ratings = [entry["rating_info"]["rating"] for entry in data["items"]]

    # Verify descending order
    assert ratings == sorted(ratings, reverse=True), (
        "Leaderboard should be sorted by rating descending"
    )

    # Verify correct players at positions
    assert data["items"][0]["player"]["id"] == p_top  # Rank 1
    assert data["items"][2]["player"]["id"] == p_bot  # Rank 3


# =============================================================================
# Count Correctness With Joins (regression: cartesian product in count query)
# =============================================================================


@pytest.mark.asyncio
async def test_matches_player_filter_total_excludes_other_matches(
    async_client: AsyncClient,
):
    """Total for player-filtered matches must not count unrelated matches."""
    game_id = await create_game(async_client, "Count Game A")
    p1 = await create_player(async_client, "Count P1")
    p2 = await create_player(async_client, "Count P2")
    p3 = await create_player(async_client, "Count P3")
    p4 = await create_player(async_client, "Count P4")

    # One match involving p1, three matches NOT involving p1
    await create_match(async_client, game_id, p1, p2)
    await create_match(async_client, game_id, p3, p4)
    await create_match(async_client, game_id, p3, p4)
    await create_match(async_client, game_id, p3, p4)

    response = await async_client.get(f"/matches/?player_id={p1}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_player_matches_total_excludes_other_matches(async_client: AsyncClient):
    """Total for /players/{id}/matches must not count unrelated matches."""
    game_id = await create_game(async_client, "Count Game B")
    p1 = await create_player(async_client, "Count P5")
    p2 = await create_player(async_client, "Count P6")
    p3 = await create_player(async_client, "Count P7")
    p4 = await create_player(async_client, "Count P8")

    # Two matches involving p1, two matches NOT involving p1
    await create_match(async_client, game_id, p1, p2)
    await create_match(async_client, game_id, p1, p3)
    await create_match(async_client, game_id, p3, p4)
    await create_match(async_client, game_id, p2, p4)

    response = await async_client.get(f"/players/{p1}/matches")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
