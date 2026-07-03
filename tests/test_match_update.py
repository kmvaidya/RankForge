# tests/test_match_update.py

"""Tests for match correction: PUT /matches/{id} and the rating recalculation
cascade, plus soft-delete recalculation on DELETE /matches/{id}.

Correctness strategy: the Glicko-2 engine is deterministic, so after a
correction the game's ratings must exactly equal those of a "control" game
where the corrected history was entered from scratch in the same order.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

# =============================================================================
# Helpers
# =============================================================================

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


async def create_game(client: AsyncClient, name: str) -> int:
    res = await client.post(
        "/games/", json={"name": name, "rating_strategy": "glicko2"}
    )
    assert res.status_code == 201
    return int(res.json()["id"])


async def create_player(client: AsyncClient, name: str) -> int:
    res = await client.post("/players/", json={"name": name})
    assert res.status_code == 201
    return int(res.json()["id"])


async def create_match(
    client: AsyncClient,
    game_id: int,
    winner_id: int,
    loser_id: int,
    played_at: datetime | None = None,
) -> dict:
    payload: dict = {
        "game_id": game_id,
        "participants": [
            {"player_id": winner_id, "team_id": 1, "outcome": {"result": "win"}},
            {"player_id": loser_id, "team_id": 2, "outcome": {"result": "loss"}},
        ],
    }
    if played_at is not None:
        payload["played_at"] = played_at.isoformat()
    res = await client.post("/matches/", json=payload)
    assert res.status_code == 201
    return dict(res.json())


async def get_ratings_by_player(client: AsyncClient, game_id: int) -> dict[int, dict]:
    """Fetch {player_id: rating_info} from the leaderboard."""
    res = await client.get(f"/games/{game_id}/leaderboard?limit=100")
    assert res.status_code == 200
    return {
        entry["player"]["id"]: entry["rating_info"] for entry in res.json()["items"]
    }


def assert_ratings_equal(
    actual: dict[int, dict],
    expected: dict[int, dict],
    id_map: dict[int, int],
) -> None:
    """Compare rating_info between two games via a player-id mapping."""
    assert len(actual) == len(id_map)
    for actual_id, expected_id in id_map.items():
        a, e = actual[actual_id], expected[expected_id]
        assert a["rating"] == pytest.approx(e["rating"], abs=0.01)
        assert a["rd"] == pytest.approx(e["rd"], abs=0.01)
        assert a["vol"] == pytest.approx(e["vol"], abs=1e-6)


# =============================================================================
# Metadata-only updates (no recalculation)
# =============================================================================


@pytest.mark.asyncio
async def test_metadata_only_update_skips_recalculation(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU Meta Game")
    p1 = await create_player(async_client, "MU Meta P1")
    p2 = await create_player(async_client, "MU Meta P2")
    match = await create_match(async_client, game_id, p1, p2)

    ratings_before = await get_ratings_by_player(async_client, game_id)

    res = await async_client.put(
        f"/matches/{match['id']}",
        json={
            "expected_version": match["version"],
            "match_metadata": {"note": "great game"},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["recalculation"] is None
    assert body["match"]["match_metadata"] == {"note": "great game"}
    assert body["match"]["version"] == match["version"] + 1

    # Ratings untouched
    assert await get_ratings_by_player(async_client, game_id) == ratings_before


@pytest.mark.asyncio
async def test_update_increments_version_each_time(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU Version Game")
    p1 = await create_player(async_client, "MU Ver P1")
    p2 = await create_player(async_client, "MU Ver P2")
    match = await create_match(async_client, game_id, p1, p2)

    res1 = await async_client.put(
        f"/matches/{match['id']}",
        json={"expected_version": 1, "match_metadata": {"n": 1}},
    )
    assert res1.status_code == 200
    assert res1.json()["match"]["version"] == 2

    res2 = await async_client.put(
        f"/matches/{match['id']}",
        json={"expected_version": 2, "match_metadata": {"n": 2}},
    )
    assert res2.status_code == 200
    assert res2.json()["match"]["version"] == 3


# =============================================================================
# Optimistic locking / not found
# =============================================================================


@pytest.mark.asyncio
async def test_stale_version_returns_409(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU Lock Game")
    p1 = await create_player(async_client, "MU Lock P1")
    p2 = await create_player(async_client, "MU Lock P2")
    match = await create_match(async_client, game_id, p1, p2)

    res = await async_client.put(
        f"/matches/{match['id']}",
        json={"expected_version": 99, "match_metadata": {}},
    )
    assert res.status_code == 409
    assert "version" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_nonexistent_match_returns_404(async_client: AsyncClient):
    res = await async_client.put(
        "/matches/999999", json={"expected_version": 1, "match_metadata": {}}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_update_deleted_match_returns_404(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU DelUpd Game")
    p1 = await create_player(async_client, "MU DelUpd P1")
    p2 = await create_player(async_client, "MU DelUpd P2")
    match = await create_match(async_client, game_id, p1, p2)

    assert (await async_client.delete(f"/matches/{match['id']}")).status_code == 204

    res = await async_client.put(
        f"/matches/{match['id']}",
        json={"expected_version": match["version"], "match_metadata": {}},
    )
    assert res.status_code == 404


# =============================================================================
# Validation
# =============================================================================


@pytest.mark.asyncio
async def test_update_with_single_participant_returns_422(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU Val Game")
    p1 = await create_player(async_client, "MU Val P1")
    p2 = await create_player(async_client, "MU Val P2")
    match = await create_match(async_client, game_id, p1, p2)

    res = await async_client.put(
        f"/matches/{match['id']}",
        json={
            "expected_version": match["version"],
            "participants": [
                {"player_id": p1, "team_id": 1, "outcome": {"result": "win"}}
            ],
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_update_with_duplicate_players_returns_422(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU Dup Game")
    p1 = await create_player(async_client, "MU Dup P1")
    p2 = await create_player(async_client, "MU Dup P2")
    match = await create_match(async_client, game_id, p1, p2)

    res = await async_client.put(
        f"/matches/{match['id']}",
        json={
            "expected_version": match["version"],
            "participants": [
                {"player_id": p1, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": p1, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_update_cannot_change_game(async_client: AsyncClient):
    """game_id is not part of MatchUpdate; sending it must be ignored."""
    game_id = await create_game(async_client, "MU NoGameChange Game")
    other_game_id = await create_game(async_client, "MU NoGameChange Other")
    p1 = await create_player(async_client, "MU NGC P1")
    p2 = await create_player(async_client, "MU NGC P2")
    match = await create_match(async_client, game_id, p1, p2)

    res = await async_client.put(
        f"/matches/{match['id']}",
        json={
            "expected_version": match["version"],
            "game_id": other_game_id,
            "match_metadata": {"tried": "game change"},
        },
    )
    assert res.status_code == 200
    assert res.json()["match"]["game_id"] == game_id


@pytest.mark.asyncio
async def test_update_too_old_match_rejected(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("MATCH_UPDATE_MAX_AGE_DAYS", "30")

    game_id = await create_game(async_client, "MU Age Game")
    p1 = await create_player(async_client, "MU Age P1")
    p2 = await create_player(async_client, "MU Age P2")
    old_time = datetime.now(timezone.utc) - timedelta(days=90)
    match = await create_match(async_client, game_id, p1, p2, played_at=old_time)

    res = await async_client.put(
        f"/matches/{match['id']}",
        json={
            "expected_version": match["version"],
            "match_metadata": {"fix": "attempt"},
        },
    )
    assert res.status_code == 422
    assert "old" in res.json()["detail"].lower()


# =============================================================================
# Rating recalculation cascade
# =============================================================================


@pytest.mark.asyncio
async def test_outcome_correction_cascades_to_subsequent_matches(
    async_client: AsyncClient,
):
    """The MASTER_PLAN scenario: flip match 1's winner, verify the whole
    chain matches a fresh replay of the corrected history."""
    game_id = await create_game(async_client, "MU Cascade Game")
    alice = await create_player(async_client, "MU Cascade Alice")
    bob = await create_player(async_client, "MU Cascade Bob")
    carol = await create_player(async_client, "MU Cascade Carol")

    m1 = await create_match(async_client, game_id, alice, bob, played_at=BASE_TIME)
    await create_match(
        async_client, game_id, bob, carol, played_at=BASE_TIME + timedelta(hours=1)
    )
    await create_match(
        async_client, game_id, carol, alice, played_at=BASE_TIME + timedelta(hours=2)
    )

    # Correct match 1: Bob actually won.
    res = await async_client.put(
        f"/matches/{m1['id']}",
        json={
            "expected_version": m1["version"],
            "participants": [
                {"player_id": bob, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": alice, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert res.status_code == 200
    recalc = res.json()["recalculation"]
    assert recalc is not None
    assert recalc["matches_recalculated"] == 3
    assert recalc["players_affected"] == 3

    # Control game: same history with the corrected outcome, entered fresh.
    control_id = await create_game(async_client, "MU Cascade Control")
    c_alice = await create_player(async_client, "MU Ctrl Alice")
    c_bob = await create_player(async_client, "MU Ctrl Bob")
    c_carol = await create_player(async_client, "MU Ctrl Carol")
    await create_match(async_client, control_id, c_bob, c_alice, played_at=BASE_TIME)
    await create_match(
        async_client,
        control_id,
        c_bob,
        c_carol,
        played_at=BASE_TIME + timedelta(hours=1),
    )
    await create_match(
        async_client,
        control_id,
        c_carol,
        c_alice,
        played_at=BASE_TIME + timedelta(hours=2),
    )

    actual = await get_ratings_by_player(async_client, game_id)
    expected = await get_ratings_by_player(async_client, control_id)
    assert_ratings_equal(actual, expected, {alice: c_alice, bob: c_bob, carol: c_carol})


@pytest.mark.asyncio
async def test_participant_swap_restores_removed_player(async_client: AsyncClient):
    """Swapping a player out of a match must revert their rating and rate
    the replacement, matching a control game."""
    game_id = await create_game(async_client, "MU Swap Game")
    a = await create_player(async_client, "MU Swap A")
    b = await create_player(async_client, "MU Swap B")
    c = await create_player(async_client, "MU Swap C")

    m1 = await create_match(async_client, game_id, a, b, played_at=BASE_TIME)

    # Correction: it was actually A vs C.
    res = await async_client.put(
        f"/matches/{m1['id']}",
        json={
            "expected_version": m1["version"],
            "participants": [
                {"player_id": a, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": c, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert res.status_code == 200

    ratings = await get_ratings_by_player(async_client, game_id)

    # B is reset to the default rating (as if they never played).
    assert ratings[b]["rating"] == pytest.approx(1500.0)
    assert ratings[b]["rd"] == pytest.approx(350.0)

    # A and C match a control game of just "A beats C".
    control_id = await create_game(async_client, "MU Swap Control")
    ca = await create_player(async_client, "MU SwapCtrl A")
    cc = await create_player(async_client, "MU SwapCtrl C")
    await create_match(async_client, control_id, ca, cc, played_at=BASE_TIME)
    expected = await get_ratings_by_player(async_client, control_id)
    assert_ratings_equal({a: ratings[a], c: ratings[c]}, expected, {a: ca, c: cc})


@pytest.mark.asyncio
async def test_played_at_change_reorders_replay(async_client: AsyncClient):
    """Moving a match earlier must replay history in the new chronological
    order, matching a control game entered in that order."""
    game_id = await create_game(async_client, "MU Reorder Game")
    a = await create_player(async_client, "MU Reorder A")
    b = await create_player(async_client, "MU Reorder B")

    await create_match(async_client, game_id, a, b, played_at=BASE_TIME)
    m2 = await create_match(
        async_client, game_id, b, a, played_at=BASE_TIME + timedelta(hours=1)
    )

    # Correction: m2 actually happened BEFORE m1.
    res = await async_client.put(
        f"/matches/{m2['id']}",
        json={
            "expected_version": m2["version"],
            "played_at": (BASE_TIME - timedelta(hours=1)).isoformat(),
        },
    )
    assert res.status_code == 200
    assert res.json()["recalculation"]["matches_recalculated"] == 2

    # Control: B beats A first, then A beats B.
    control_id = await create_game(async_client, "MU Reorder Control")
    ca = await create_player(async_client, "MU ReorderCtrl A")
    cb = await create_player(async_client, "MU ReorderCtrl B")
    await create_match(
        async_client, control_id, cb, ca, played_at=BASE_TIME - timedelta(hours=1)
    )
    await create_match(async_client, control_id, ca, cb, played_at=BASE_TIME)

    actual = await get_ratings_by_player(async_client, game_id)
    expected = await get_ratings_by_player(async_client, control_id)
    assert_ratings_equal(actual, expected, {a: ca, b: cb})


@pytest.mark.asyncio
async def test_recalculation_rewrites_rating_history(async_client: AsyncClient):
    """After a cascade, subsequent matches' rating_info_before must reflect
    the corrected timeline."""
    game_id = await create_game(async_client, "MU History Game")
    a = await create_player(async_client, "MU Hist A")
    b = await create_player(async_client, "MU Hist B")

    m1 = await create_match(async_client, game_id, a, b, played_at=BASE_TIME)
    m2 = await create_match(
        async_client, game_id, a, b, played_at=BASE_TIME + timedelta(hours=1)
    )

    # Flip m1's outcome.
    res = await async_client.put(
        f"/matches/{m1['id']}",
        json={
            "expected_version": m1["version"],
            "participants": [
                {"player_id": b, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": a, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert res.status_code == 200

    # m2's stored "before" ratings must now show A below 1500 (A lost m1).
    m2_res = await async_client.get(f"/matches/{m2['id']}")
    assert m2_res.status_code == 200
    for participant in m2_res.json()["participants"]:
        before = participant["rating_info_before"]
        if participant["player_id"] == a:
            assert before["rating"] < 1500.0
        else:
            assert before["rating"] > 1500.0


# =============================================================================
# Soft delete with recalculation
# =============================================================================


@pytest.mark.asyncio
async def test_delete_match_reverts_ratings(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU DelRevert Game")
    p1 = await create_player(async_client, "MU DelRev P1")
    p2 = await create_player(async_client, "MU DelRev P2")
    match = await create_match(async_client, game_id, p1, p2, played_at=BASE_TIME)

    assert (await async_client.delete(f"/matches/{match['id']}")).status_code == 204

    # Match hidden from reads
    assert (await async_client.get(f"/matches/{match['id']}")).status_code == 404
    list_res = await async_client.get(f"/matches/?game_id={game_id}")
    assert list_res.json()["total"] == 0

    # Ratings back to default, as if the match never happened
    ratings = await get_ratings_by_player(async_client, game_id)
    for pid in (p1, p2):
        assert ratings[pid]["rating"] == pytest.approx(1500.0)
        assert ratings[pid]["rd"] == pytest.approx(350.0)


@pytest.mark.asyncio
async def test_delete_middle_match_recalculates_chain(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU DelMid Game")
    a = await create_player(async_client, "MU DelMid A")
    b = await create_player(async_client, "MU DelMid B")

    await create_match(async_client, game_id, a, b, played_at=BASE_TIME)
    m2 = await create_match(
        async_client, game_id, b, a, played_at=BASE_TIME + timedelta(hours=1)
    )
    await create_match(
        async_client, game_id, a, b, played_at=BASE_TIME + timedelta(hours=2)
    )

    assert (await async_client.delete(f"/matches/{m2['id']}")).status_code == 204

    # Control: only m1 and m3.
    control_id = await create_game(async_client, "MU DelMid Control")
    ca = await create_player(async_client, "MU DelMidCtrl A")
    cb = await create_player(async_client, "MU DelMidCtrl B")
    await create_match(async_client, control_id, ca, cb, played_at=BASE_TIME)
    await create_match(
        async_client, control_id, ca, cb, played_at=BASE_TIME + timedelta(hours=2)
    )

    actual = await get_ratings_by_player(async_client, game_id)
    expected = await get_ratings_by_player(async_client, control_id)
    assert_ratings_equal(actual, expected, {a: ca, b: cb})


@pytest.mark.asyncio
async def test_delete_already_deleted_match_returns_404(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU DelTwice Game")
    p1 = await create_player(async_client, "MU DelTwice P1")
    p2 = await create_player(async_client, "MU DelTwice P2")
    match = await create_match(async_client, game_id, p1, p2)

    assert (await async_client.delete(f"/matches/{match['id']}")).status_code == 204
    assert (await async_client.delete(f"/matches/{match['id']}")).status_code == 404


# =============================================================================
# Stats maintenance and full-game recalculation
# =============================================================================


@pytest.mark.asyncio
async def test_match_creation_updates_stats(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU Stats Game")
    p1 = await create_player(async_client, "MU Stats P1")
    p2 = await create_player(async_client, "MU Stats P2")

    await create_match(async_client, game_id, p1, p2)
    await create_match(async_client, game_id, p1, p2)
    await create_match(async_client, game_id, p2, p1)

    res = await async_client.get(f"/players/{p1}/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["total_matches"] == 3
    assert body["total_wins"] == 2
    assert body["total_losses"] == 1
    assert body["overall_win_rate"] == pytest.approx(2 / 3, abs=1e-3)

    lb = await async_client.get(f"/games/{game_id}/leaderboard")
    entry = next(e for e in lb.json()["items"] if e["player"]["id"] == p1)
    assert entry["stats"]["matches_played"] == 3
    assert entry["stats"]["wins"] == 2


@pytest.mark.asyncio
async def test_draw_counted_in_stats(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU DrawStats Game")
    p1 = await create_player(async_client, "MU DrawStats P1")
    p2 = await create_player(async_client, "MU DrawStats P2")

    res = await async_client.post(
        "/matches/",
        json={
            "game_id": game_id,
            "participants": [
                {"player_id": p1, "team_id": 1, "outcome": {"result": "draw"}},
                {"player_id": p2, "team_id": 2, "outcome": {"result": "draw"}},
            ],
        },
    )
    assert res.status_code == 201

    stats = (await async_client.get(f"/players/{p1}/stats")).json()
    assert stats["total_matches"] == 1
    assert stats["total_draws"] == 1
    assert stats["total_wins"] == 0


@pytest.mark.asyncio
async def test_delete_match_rebuilds_stats(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU DelStats Game")
    p1 = await create_player(async_client, "MU DelStats P1")
    p2 = await create_player(async_client, "MU DelStats P2")

    await create_match(async_client, game_id, p1, p2, played_at=BASE_TIME)
    m2 = await create_match(
        async_client, game_id, p1, p2, played_at=BASE_TIME + timedelta(hours=1)
    )

    assert (await async_client.delete(f"/matches/{m2['id']}")).status_code == 204

    stats = (await async_client.get(f"/players/{p1}/stats")).json()
    assert stats["total_matches"] == 1
    assert stats["total_wins"] == 1


@pytest.mark.asyncio
async def test_update_participants_rebuilds_stats(async_client: AsyncClient):
    game_id = await create_game(async_client, "MU UpdStats Game")
    p1 = await create_player(async_client, "MU UpdStats P1")
    p2 = await create_player(async_client, "MU UpdStats P2")
    m1 = await create_match(async_client, game_id, p1, p2, played_at=BASE_TIME)

    # Flip the winner
    res = await async_client.put(
        f"/matches/{m1['id']}",
        json={
            "expected_version": m1["version"],
            "participants": [
                {"player_id": p2, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": p1, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert res.status_code == 200

    p1_stats = (await async_client.get(f"/players/{p1}/stats")).json()
    assert p1_stats["total_matches"] == 1
    assert p1_stats["total_wins"] == 0
    assert p1_stats["total_losses"] == 1
    p2_stats = (await async_client.get(f"/players/{p2}/stats")).json()
    assert p2_stats["total_wins"] == 1


@pytest.mark.asyncio
async def test_recalculate_game_heals_corrupted_data(async_client: AsyncClient):
    """POST /games/{id}/recalculate must restore ratings and stats to what
    a clean replay produces."""
    game_id = await create_game(async_client, "MU Heal Game")
    p1 = await create_player(async_client, "MU Heal P1")
    p2 = await create_player(async_client, "MU Heal P2")
    await create_match(async_client, game_id, p1, p2, played_at=BASE_TIME)
    await create_match(
        async_client, game_id, p1, p2, played_at=BASE_TIME + timedelta(hours=1)
    )

    healthy = await get_ratings_by_player(async_client, game_id)

    res = await async_client.post(f"/games/{game_id}/recalculate")
    assert res.status_code == 200
    body = res.json()
    assert body["matches_recalculated"] == 2
    assert body["players_affected"] == 2

    # Ratings unchanged by a clean recalculation (deterministic replay)
    assert await get_ratings_by_player(async_client, game_id) == healthy

    # Stats correct after rebuild
    stats = (await async_client.get(f"/players/{p1}/stats")).json()
    assert stats["total_matches"] == 2
    assert stats["total_wins"] == 2


@pytest.mark.asyncio
async def test_recalculate_nonexistent_game_returns_404(async_client: AsyncClient):
    res = await async_client.post("/games/999999/recalculate")
    assert res.status_code == 404


# =============================================================================
# Review regression tests (2026-07-03 multi-angle review findings)
# =============================================================================


@pytest.mark.asyncio
async def test_timezone_aware_played_at_is_normalized_and_cascades(
    async_client: AsyncClient,
):
    """A match sent with a non-UTC offset must be stored as naive UTC so the
    cascade window (SQL comparison) still includes it.

    Regression: '2025-01-01T03:00:00-08:00' (= 11:00 UTC) stored verbatim
    compared lexically below a naive boundary and was silently dropped from
    replay."""
    game_id = await create_game(async_client, "MU TZ Game")
    p1 = await create_player(async_client, "MU TZ P1")
    p2 = await create_player(async_client, "MU TZ P2")

    m1 = await create_match(
        async_client,
        game_id,
        p1,
        p2,
        played_at=datetime(2025, 1, 1, 10, 0, 0),  # naive
    )
    # Played chronologically AFTER m1 (11:00 UTC), sent with a -08:00 offset
    m2_res = await async_client.post(
        "/matches/",
        json={
            "game_id": game_id,
            "played_at": "2025-01-01T03:00:00-08:00",
            "participants": [
                {"player_id": p1, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": p2, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert m2_res.status_code == 201
    # Stored/returned as naive UTC
    assert m2_res.json()["played_at"] == "2025-01-01T11:00:00"

    # Correcting m1 must replay BOTH matches
    res = await async_client.put(
        f"/matches/{m1['id']}",
        json={
            "expected_version": m1["version"],
            "participants": [
                {"player_id": p2, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": p1, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert res.status_code == 200
    assert res.json()["recalculation"]["matches_recalculated"] == 2


@pytest.mark.asyncio
async def test_swapped_in_player_gets_stats(async_client: AsyncClient):
    """A player added to a match via PUT must get stats, not just a rating.

    Regression: rebuild scope was captured pre-mutation, skipping new
    participants."""
    game_id = await create_game(async_client, "MU SwapStats Game")
    a = await create_player(async_client, "MU SwapStats A")
    b = await create_player(async_client, "MU SwapStats B")
    c = await create_player(async_client, "MU SwapStats C")
    m1 = await create_match(async_client, game_id, a, b, played_at=BASE_TIME)

    res = await async_client.put(
        f"/matches/{m1['id']}",
        json={
            "expected_version": m1["version"],
            "participants": [
                {"player_id": a, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": c, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert res.status_code == 200
    # a, b (removed), and c (added) are all affected
    assert res.json()["recalculation"]["players_affected"] == 3

    c_stats = (await async_client.get(f"/players/{c}/stats")).json()
    assert c_stats["total_matches"] == 1
    assert c_stats["total_losses"] == 1
    b_stats = (await async_client.get(f"/players/{b}/stats")).json()
    assert b_stats["total_matches"] == 0


@pytest.mark.asyncio
async def test_backdated_match_creation_replays_history(async_client: AsyncClient):
    """Creating a match earlier than existing matches must replay the window
    so ratings equal chronological entry.

    Regression: backdated matches were rated against current profiles and
    only appended, silently corrupting history until a manual recalculate."""
    game_id = await create_game(async_client, "MU Backdate Game")
    a = await create_player(async_client, "MU Backdate A")
    b = await create_player(async_client, "MU Backdate B")

    # Entered out of order: the later match first
    await create_match(
        async_client, game_id, a, b, played_at=BASE_TIME + timedelta(hours=1)
    )
    await create_match(async_client, game_id, b, a, played_at=BASE_TIME)

    # Control: same history entered chronologically
    control_id = await create_game(async_client, "MU Backdate Control")
    ca = await create_player(async_client, "MU BackdateCtrl A")
    cb = await create_player(async_client, "MU BackdateCtrl B")
    await create_match(async_client, control_id, cb, ca, played_at=BASE_TIME)
    await create_match(
        async_client, control_id, ca, cb, played_at=BASE_TIME + timedelta(hours=1)
    )

    actual = await get_ratings_by_player(async_client, game_id)
    expected = await get_ratings_by_player(async_client, control_id)
    assert_ratings_equal(actual, expected, {a: ca, b: cb})


@pytest.mark.asyncio
async def test_soft_deleted_player_rejected_in_new_match(
    async_client: AsyncClient, db_session
):
    """Soft-deleted players must not be recordable into new matches."""
    from rankforge.db import models

    game_id = await create_game(async_client, "MU DelPlayer Game")
    p1 = await create_player(async_client, "MU DelPlayer P1")
    p2 = await create_player(async_client, "MU DelPlayer P2")

    # Soft-delete p2 directly (the API currently hard-deletes)
    player = await db_session.get(models.Player, p2)
    player.deleted_at = models.utcnow_naive()
    await db_session.commit()

    res = await async_client.post(
        "/matches/",
        json={
            "game_id": game_id,
            "participants": [
                {"player_id": p1, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": p2, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_stats_rebuild_preserves_custom_keys(
    async_client: AsyncClient, db_session
):
    """A correction-triggered stats rebuild must not destroy game-specific
    custom stats keys (the schema documents them as supported)."""
    from sqlalchemy import select as sa_select

    from rankforge.db import models

    game_id = await create_game(async_client, "MU CustomStats Game")
    p1 = await create_player(async_client, "MU CustomStats P1")
    p2 = await create_player(async_client, "MU CustomStats P2")
    await create_match(async_client, game_id, p1, p2, played_at=BASE_TIME)
    m2 = await create_match(
        async_client, game_id, p1, p2, played_at=BASE_TIME + timedelta(hours=1)
    )

    # Plant a custom stats key (e.g. from an import script)
    profile = (
        await db_session.execute(
            sa_select(models.GameProfile).where(
                models.GameProfile.player_id == p1,
                models.GameProfile.game_id == game_id,
            )
        )
    ).scalar_one()
    profile.stats = {**profile.stats, "spymaster_wins": 4}
    await db_session.commit()

    # Trigger a rebuild via deletion
    assert (await async_client.delete(f"/matches/{m2['id']}")).status_code == 204

    await db_session.refresh(profile)
    assert profile.stats["spymaster_wins"] == 4
    assert profile.stats["matches_played"] == 1
