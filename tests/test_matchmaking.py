# tests/test_matchmaking.py

"""Tests for the matchmaking algorithm and POST /matchmaking/generate.

Covers the pure math (team superposition, fairness), both search modes
(exhaustive and simulated annealing), constraint handling, and the API.
"""

import time

import pytest
from httpx import AsyncClient

from rankforge.exceptions import InfeasibleConstraintsError
from rankforge.services.matchmaking_service import (
    PlayerSkill,
    configuration_fairness,
    pairwise_fairness,
    search_configurations,
    team_distribution,
    win_probability,
)

# =============================================================================
# Pure math
# =============================================================================


def skill(pid: int, mu: float, sigma: float = 100.0) -> PlayerSkill:
    return PlayerSkill(player_id=pid, mu=mu, sigma=sigma)


def test_team_distribution_superposition():
    mu, sigma = team_distribution([skill(1, 1500, 30), skill(2, 1700, 40)])
    assert mu == 3200
    assert sigma == pytest.approx(50.0)  # sqrt(30^2 + 40^2)


def test_win_probability_equal_teams_is_half():
    a = (3000.0, 100.0)
    assert win_probability(a, a) == pytest.approx(0.5)


def test_win_probability_stronger_team_above_half():
    strong, weak = (3200.0, 100.0), (3000.0, 100.0)
    p = win_probability(strong, weak)
    assert p > 0.5
    # Symmetry: P(A beats B) + P(B beats A) = 1
    assert p + win_probability(weak, strong) == pytest.approx(1.0)


def test_fairness_perfectly_matched_is_one():
    a = (3000.0, 120.0)
    assert pairwise_fairness(a, a) == pytest.approx(1.0)


def test_fairness_decreases_with_rating_gap():
    base = (3000.0, 100.0)
    gaps = [0, 100, 300, 800]
    scores = [pairwise_fairness(base, (3000.0 + g, 100.0)) for g in gaps]
    assert scores == sorted(scores, reverse=True)
    assert scores[-1] < 0.1  # 800-point gap is a foregone conclusion


def test_configuration_fairness_uses_worst_pair():
    # Three teams: two equal, one much stronger
    teams = [
        [skill(1, 1500)],
        [skill(2, 1500)],
        [skill(3, 2500)],
    ]
    fairness = configuration_fairness(teams)
    # Worst pairing (1500 vs 2500) dominates
    assert fairness == pytest.approx(pairwise_fairness((1500, 100.0), (2500, 100.0)))


# =============================================================================
# Exhaustive search
# =============================================================================


def test_exhaustive_finds_optimal_split():
    """4 players with ratings 1000/1200/1400/1600: the balanced split is
    (1000+1600) vs (1200+1400)."""
    skills = {
        1: skill(1, 1000),
        2: skill(2, 1200),
        3: skill(3, 1400),
        4: skill(4, 1600),
    }
    ranked, method, _ = search_configurations(
        skills, [1, 2, 3, 4], [2, 2], num_results=3, together=[], apart=[]
    )
    assert method == "exhaustive"
    best_fairness, best_config = ranked[0]
    teams = {frozenset(team) for team in best_config}
    assert teams == {frozenset({1, 4}), frozenset({2, 3})}
    assert best_fairness == pytest.approx(1.0)  # 2600 vs 2600


def test_exhaustive_results_sorted_by_fairness():
    skills = {i: skill(i, 1000 + i * 137) for i in range(1, 7)}
    ranked, _, _ = search_configurations(
        skills, list(skills), [3, 3], num_results=5, together=[], apart=[]
    )
    scores = [fairness for fairness, _ in ranked]
    assert scores == sorted(scores, reverse=True)
    assert len(ranked) <= 5


def test_exhaustive_deduplicates_team_order():
    """[A,B] vs [C,D] and [C,D] vs [A,B] are the same configuration."""
    skills = {i: skill(i, 1500) for i in range(1, 5)}
    ranked, _, _ = search_configurations(
        skills, [1, 2, 3, 4], [2, 2], num_results=20, together=[], apart=[]
    )
    # 4 players into two pairs: exactly 3 distinct configurations
    assert len(ranked) == 3


def test_together_constraint_respected():
    skills = {i: skill(i, 1000 + i * 100) for i in range(1, 5)}
    ranked, _, _ = search_configurations(
        skills,
        [1, 2, 3, 4],
        [2, 2],
        num_results=10,
        together=[{1, 2}],
        apart=[],
    )
    for _, config in ranked:
        for team in config:
            if 1 in team:
                assert 2 in team


def test_apart_constraint_respected():
    skills = {i: skill(i, 1000 + i * 100) for i in range(1, 5)}
    ranked, _, _ = search_configurations(
        skills,
        [1, 2, 3, 4],
        [2, 2],
        num_results=10,
        together=[],
        apart=[{1, 2}],
    )
    for _, config in ranked:
        for team in config:
            assert not ({1, 2} <= set(team))


def test_conflicting_constraints_raise():
    skills = {i: skill(i, 1500) for i in range(1, 5)}
    with pytest.raises(InfeasibleConstraintsError):
        search_configurations(
            skills,
            [1, 2, 3, 4],
            [2, 2],
            num_results=5,
            together=[{1, 2}],
            apart=[{1, 2}],
        )


def test_uneven_team_sizes():
    skills = {i: skill(i, 1500) for i in range(1, 6)}
    ranked, _, _ = search_configurations(
        skills, [1, 2, 3, 4, 5], [3, 2], num_results=5, together=[], apart=[]
    )
    for _, config in ranked:
        assert sorted(len(team) for team in config) == [2, 3]


def test_three_team_configuration():
    skills = {i: skill(i, 1000 + i * 50) for i in range(1, 7)}
    ranked, _, _ = search_configurations(
        skills, list(skills), [2, 2, 2], num_results=5, together=[], apart=[]
    )
    assert ranked
    for _, config in ranked:
        assert len(config) == 3
        assert {pid for team in config for pid in team} == set(skills)


# =============================================================================
# Simulated annealing (large N)
# =============================================================================


def test_annealing_used_for_large_pools_and_finds_balance():
    """18 players in two teams of 9: 48620 ordered partitions > limit."""
    skills = {i: skill(i, 1000 + i * 61, 80.0) for i in range(1, 19)}
    start = time.monotonic()
    ranked, method, _ = search_configurations(
        skills,
        list(skills),
        [9, 9],
        num_results=5,
        together=[],
        apart=[],
        seed=42,
    )
    elapsed = time.monotonic() - start
    assert method == "annealing"
    assert elapsed < 5.0
    best_fairness, best_config = ranked[0]
    # Theoretical optimum here is ~0.857: rating steps of 61 with an odd
    # total mean the best split differs by exactly 61 points. Annealing
    # should get at or near that optimum.
    assert best_fairness > 0.85
    assert {pid for team in best_config for pid in team} == set(skills)
    assert [len(t) for t in best_config] == [9, 9]


def test_annealing_respects_constraints():
    skills = {i: skill(i, 1000 + i * 61, 80.0) for i in range(1, 19)}
    ranked, method, _ = search_configurations(
        skills,
        list(skills),
        [9, 9],
        num_results=5,
        together=[{1, 2, 3}],
        apart=[{4, 5}],
        seed=7,
    )
    assert method == "annealing"
    for _, config in ranked:
        for team in config:
            team_set = set(team)
            if 1 in team_set:
                assert {2, 3} <= team_set
            assert not ({4, 5} <= team_set)


def test_annealing_reproducible_with_seed():
    skills = {i: skill(i, 1000 + i * 61, 80.0) for i in range(1, 19)}
    args = dict(num_results=3, together=[], apart=[])
    r1, _, _ = search_configurations(skills, list(skills), [9, 9], seed=123, **args)
    r2, _, _ = search_configurations(skills, list(skills), [9, 9], seed=123, **args)
    assert r1 == r2


# =============================================================================
# API
# =============================================================================


async def _setup_players(
    client: AsyncClient, game_name: str, names_and_wins: list[tuple[str, int]]
) -> tuple[int, dict[str, int]]:
    """Create a game and players; give each player N wins vs a filler player
    to spread their ratings."""
    res = await client.post(
        "/games/", json={"name": game_name, "rating_strategy": "glicko2"}
    )
    game_id = int(res.json()["id"])

    ids: dict[str, int] = {}
    for name, _ in names_and_wins:
        res = await client.post("/players/", json={"name": name})
        assert res.status_code == 201
        ids[name] = int(res.json()["id"])

    filler_res = await client.post("/players/", json={"name": f"{game_name} Filler"})
    filler_id = int(filler_res.json()["id"])

    for name, wins in names_and_wins:
        for _ in range(wins):
            res = await client.post(
                "/matches/",
                json={
                    "game_id": game_id,
                    "participants": [
                        {
                            "player_id": ids[name],
                            "team_id": 1,
                            "outcome": {"result": "win"},
                        },
                        {
                            "player_id": filler_id,
                            "team_id": 2,
                            "outcome": {"result": "loss"},
                        },
                    ],
                },
            )
            assert res.status_code == 201

    return game_id, ids


@pytest.mark.asyncio
async def test_generate_endpoint_returns_ranked_configurations(
    async_client: AsyncClient,
):
    game_id, ids = await _setup_players(
        async_client,
        "MM API Game",
        [("MM A", 0), ("MM B", 2), ("MM C", 4), ("MM D", 6)],
    )

    res = await async_client.post(
        "/matchmaking/generate",
        json={
            "game_id": game_id,
            "player_ids": list(ids.values()),
            "num_results": 3,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["method"] == "exhaustive"
    assert 1 <= len(body["configurations"]) <= 3

    scores = [c["fairness"] for c in body["configurations"]]
    assert scores == sorted(scores, reverse=True)

    best = body["configurations"][0]
    assert len(best["teams"]) == 2
    assert len(best["team_ratings"]) == 2
    assert len(best["win_probabilities"]) == 2
    all_ids = {m["player"]["id"] for team in best["teams"] for m in team}
    assert all_ids == set(ids.values())


@pytest.mark.asyncio
async def test_generate_players_without_profiles_use_default_rating(
    async_client: AsyncClient,
):
    """Brand-new players (no matches yet) can still be matched."""
    res = await async_client.post(
        "/games/", json={"name": "MM Fresh Game", "rating_strategy": "glicko2"}
    )
    game_id = int(res.json()["id"])

    ids = []
    for name in ["MM Fresh A", "MM Fresh B", "MM Fresh C", "MM Fresh D"]:
        res = await async_client.post("/players/", json={"name": name})
        ids.append(int(res.json()["id"]))

    res = await async_client.post(
        "/matchmaking/generate", json={"game_id": game_id, "player_ids": ids}
    )
    assert res.status_code == 200
    best = res.json()["configurations"][0]
    # All fresh players: every split is perfectly fair
    assert best["fairness"] == pytest.approx(1.0)
    for team in best["teams"]:
        for member in team:
            assert member["rating"] == pytest.approx(1500.0)


@pytest.mark.asyncio
async def test_generate_nonexistent_game_returns_404(async_client: AsyncClient):
    res = await async_client.post("/players/", json={"name": "MM NoGame P"})
    pid = int(res.json()["id"])
    res = await async_client.post(
        "/matchmaking/generate",
        json={"game_id": 999999, "player_ids": [pid, pid + 1]},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_generate_nonexistent_player_returns_404(async_client: AsyncClient):
    res = await async_client.post(
        "/games/", json={"name": "MM NoPlayer Game", "rating_strategy": "glicko2"}
    )
    game_id = int(res.json()["id"])
    res = await async_client.post(
        "/matchmaking/generate",
        json={"game_id": game_id, "player_ids": [999998, 999999]},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_generate_duplicate_players_returns_422(async_client: AsyncClient):
    res = await async_client.post(
        "/games/", json={"name": "MM Dup Game", "rating_strategy": "glicko2"}
    )
    game_id = int(res.json()["id"])
    res = await async_client.post("/players/", json={"name": "MM Dup P"})
    pid = int(res.json()["id"])
    res = await async_client.post(
        "/matchmaking/generate", json={"game_id": game_id, "player_ids": [pid, pid]}
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_generate_bad_team_sizes_returns_422(async_client: AsyncClient):
    res = await async_client.post(
        "/games/", json={"name": "MM Sizes Game", "rating_strategy": "glicko2"}
    )
    game_id = int(res.json()["id"])
    ids = []
    for name in ["MM Sz A", "MM Sz B", "MM Sz C"]:
        res = await async_client.post("/players/", json={"name": name})
        ids.append(int(res.json()["id"]))

    res = await async_client.post(
        "/matchmaking/generate",
        json={
            "game_id": game_id,
            "player_ids": ids,
            "team_count": 2,
            "team_sizes": [2, 2],  # sums to 4 != 3 players
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_generate_infeasible_constraints_returns_422(
    async_client: AsyncClient,
):
    res = await async_client.post(
        "/games/", json={"name": "MM Infeasible Game", "rating_strategy": "glicko2"}
    )
    game_id = int(res.json()["id"])
    ids = []
    for name in ["MM Inf A", "MM Inf B", "MM Inf C", "MM Inf D"]:
        res = await async_client.post("/players/", json={"name": name})
        ids.append(int(res.json()["id"]))

    res = await async_client.post(
        "/matchmaking/generate",
        json={
            "game_id": game_id,
            "player_ids": ids,
            "constraints": {
                "together": [[ids[0], ids[1]]],
                "apart": [[ids[0], ids[1]]],
            },
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_generate_twelve_players_under_two_seconds(
    async_client: AsyncClient,
):
    """MASTER_PLAN performance criterion: 12 players < 2 seconds."""
    res = await async_client.post(
        "/games/", json={"name": "MM Perf Game", "rating_strategy": "glicko2"}
    )
    game_id = int(res.json()["id"])
    ids = []
    for i in range(12):
        res = await async_client.post("/players/", json={"name": f"MM Perf {i}"})
        ids.append(int(res.json()["id"]))

    start = time.monotonic()
    res = await async_client.post(
        "/matchmaking/generate",
        json={"game_id": game_id, "player_ids": ids, "num_results": 5},
    )
    elapsed = time.monotonic() - start
    assert res.status_code == 200
    assert elapsed < 2.0
    assert res.json()["configurations"]
