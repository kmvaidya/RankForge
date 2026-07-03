# src/rankforge/services/matchmaking_service.py

"""Balanced team generation via skill-distribution superposition.

The algorithm (MASTER_PLAN Phase 1):

1. Model each player's skill as a Gaussian N(mu=rating, sigma=rd) from their
   Glicko-2 profile.
2. A team's skill is the superposition (sum) of its members' distributions:
   N(sum(mu_i), sqrt(sum(sigma_i^2))).
3. Fairness of a two-team matchup: with D = Team1 - Team2 ~ N(mu_D, sigma_D),
   P(Team1 outrates Team2) = Phi(mu_D / sigma_D). Fairness is how close that
   is to a coin flip: fairness = 1 - |2*Phi(mu_D/sigma_D) - 1|, which is 1.0
   for perfectly matched teams and approaches 0 for a foregone conclusion.
   For M > 2 teams, the configuration's fairness is the minimum pairwise
   fairness (the worst matchup bounds the experience).
4. Search: exhaustively enumerate all partitions when the space is small
   (<= EXHAUSTIVE_LIMIT partitions), otherwise run simulated annealing with
   player-swap perturbations.

Constraints ("must play together" groups and "keep apart" groups) are
enforced as hard validity filters in both search modes.

Pure math helpers take (mu, sigma) tuples so they're trivially unit-testable
without a database.
"""

from __future__ import annotations

import itertools
import logging
import math
import random
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rankforge.db import models
from rankforge.db.models import DEFAULT_RATING_INFO
from rankforge.exceptions import (
    GameNotFoundError,
    InfeasibleConstraintsError,
    PlayerNotFoundError,
)
from rankforge.schemas import matchmaking as mm_schema
from rankforge.schemas.player import PlayerRead

logger = logging.getLogger(__name__)

# Search configuration (see MASTER_PLAN "Matchmaking Algorithm").
EXHAUSTIVE_LIMIT = 20_000  # max partitions to enumerate before annealing
ANNEALING_CONFIG = {
    "t_max": 1.0,
    "t_min": 0.001,
    "cooling_rate": 0.99,
    "iterations_per_temp": 10,
    "restarts": 4,
}


# =============================================================================
# Pure math: distributions and fairness
# =============================================================================


@dataclass(frozen=True)
class PlayerSkill:
    """A player's skill distribution N(mu, sigma)."""

    player_id: int
    mu: float
    sigma: float


def team_distribution(members: list[PlayerSkill]) -> tuple[float, float]:
    """Superpose member skills into a team distribution N(mu, sigma)."""
    mu = sum(m.mu for m in members)
    sigma = math.sqrt(sum(m.sigma**2 for m in members))
    return mu, sigma


def _phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def win_probability(team_a: tuple[float, float], team_b: tuple[float, float]) -> float:
    """P(team_a outrates team_b) for two team distributions."""
    mu_diff = team_a[0] - team_b[0]
    sigma_diff = math.sqrt(team_a[1] ** 2 + team_b[1] ** 2)
    if sigma_diff == 0:
        return 0.5 if mu_diff == 0 else (1.0 if mu_diff > 0 else 0.0)
    return _phi(mu_diff / sigma_diff)


def pairwise_fairness(
    team_a: tuple[float, float], team_b: tuple[float, float]
) -> float:
    """Fairness of one matchup: 1.0 = coin flip, ~0.0 = foregone conclusion."""
    p = win_probability(team_a, team_b)
    return 1.0 - abs(2.0 * p - 1.0)


def configuration_fairness(teams: list[list[PlayerSkill]]) -> float:
    """Fairness of a full configuration: the worst pairwise matchup."""
    distributions = [team_distribution(team) for team in teams]
    return min(
        pairwise_fairness(a, b) for a, b in itertools.combinations(distributions, 2)
    )


# =============================================================================
# Constraints
# =============================================================================


def _satisfies_constraints(
    teams: tuple[tuple[int, ...], ...],
    together: list[set[int]],
    apart: list[set[int]],
) -> bool:
    """Check hard constraints against a configuration of player-id teams."""
    team_of: dict[int, int] = {}
    for team_index, team in enumerate(teams):
        for player_id in team:
            team_of[player_id] = team_index

    for group in together:
        team_indexes = {team_of[pid] for pid in group if pid in team_of}
        if len(team_indexes) > 1:
            return False

    for group in apart:
        seen_teams: set[int] = set()
        for pid in group:
            if pid not in team_of:
                continue
            if team_of[pid] in seen_teams:
                return False
            seen_teams.add(team_of[pid])

    return True


def _canonical(teams: list[list[int]] | tuple[tuple[int, ...], ...]) -> tuple:
    """Canonical form for dedup: sorted members, teams sorted by size then ids.

    Same-size teams are interchangeable (fairness doesn't depend on team
    labels), so [A,B] vs [C,D] equals [C,D] vs [A,B].
    """
    return tuple(
        sorted(
            (tuple(sorted(team)) for team in teams),
            key=lambda t: (len(t), t),
        )
    )


# =============================================================================
# Search: exhaustive enumeration
# =============================================================================


def _partition_count(n: int, sizes: list[int]) -> int:
    """Number of ordered partitions (multinomial coefficient).

    Counts team-labeled assignments; same-size team permutations are
    deduplicated later via canonical forms, so this slightly overestimates
    the distinct search space. Used only for the exhaustive-vs-annealing
    decision.
    """
    total = math.factorial(n)
    for size in sizes:
        total //= math.factorial(size)
    return total


def _enumerate_partitions(
    player_ids: list[int], sizes: list[int]
) -> Iterator[tuple[tuple[int, ...], ...]]:
    """Yield all ordered partitions of player_ids into teams of the given sizes.

    Permutations of same-size teams appear multiple times; the top-N
    collector deduplicates them via canonical forms.
    """

    def helper(
        remaining: tuple[int, ...], sizes_left: tuple[int, ...]
    ) -> Iterator[tuple[tuple[int, ...], ...]]:
        if not sizes_left:
            yield ()
            return
        size = sizes_left[0]
        for team in itertools.combinations(remaining, size):
            team_set = set(team)
            remaining_after = tuple(p for p in remaining if p not in team_set)
            for tail in helper(remaining_after, sizes_left[1:]):
                yield (team, *tail)

    yield from helper(tuple(sorted(player_ids)), tuple(sizes))


# =============================================================================
# Search: simulated annealing
# =============================================================================


def _random_valid_configuration(
    rng: random.Random,
    player_ids: list[int],
    sizes: list[int],
    together: list[set[int]],
    apart: list[set[int]],
    max_attempts: int = 2000,
) -> tuple[tuple[int, ...], ...] | None:
    """Sample a random partition satisfying the constraints, or None."""
    for _ in range(max_attempts):
        shuffled = player_ids.copy()
        rng.shuffle(shuffled)
        teams: list[tuple[int, ...]] = []
        index = 0
        for size in sizes:
            teams.append(tuple(shuffled[index : index + size]))
            index += size
        config = tuple(teams)
        if _satisfies_constraints(config, together, apart):
            return config
    return None


def _swap_players(
    rng: random.Random, config: tuple[tuple[int, ...], ...]
) -> tuple[tuple[int, ...], ...]:
    """Perturb: swap one random player between two random distinct teams."""
    team_indexes = rng.sample(range(len(config)), 2)
    a, b = team_indexes[0], team_indexes[1]
    player_a = rng.randrange(len(config[a]))
    player_b = rng.randrange(len(config[b]))
    teams = [list(team) for team in config]
    teams[a][player_a], teams[b][player_b] = teams[b][player_b], teams[a][player_a]
    return tuple(tuple(team) for team in teams)


# =============================================================================
# Top-N collection
# =============================================================================


class _TopConfigurations:
    """Keeps the N best distinct configurations by fairness."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._by_key: dict[tuple, tuple[float, tuple[tuple[int, ...], ...]]] = {}

    def offer(self, config: tuple[tuple[int, ...], ...], fairness: float) -> None:
        key = _canonical(config)
        existing = self._by_key.get(key)
        if existing is None or fairness > existing[0]:
            self._by_key[key] = (fairness, config)
        if len(self._by_key) > self._limit * 4:
            self._prune()

    def _prune(self) -> None:
        best = sorted(self._by_key.items(), key=lambda kv: -kv[1][0])
        self._by_key = dict(best[: self._limit])

    def best(self) -> list[tuple[float, tuple[tuple[int, ...], ...]]]:
        ranked = sorted(self._by_key.values(), key=lambda fc: -fc[0])
        return ranked[: self._limit]


# =============================================================================
# Search drivers
# =============================================================================


def search_configurations(
    skills: dict[int, PlayerSkill],
    player_ids: list[int],
    sizes: list[int],
    num_results: int,
    together: list[set[int]],
    apart: list[set[int]],
    seed: int | None = None,
) -> tuple[list[tuple[float, tuple[tuple[int, ...], ...]]], str, int]:
    """Find the most balanced configurations.

    Returns (ranked [(fairness, config)], method, configurations_evaluated).
    Raises InfeasibleConstraintsError if no valid configuration exists (or
    none was found within the annealing budget).
    """

    def fairness_of(config: tuple[tuple[int, ...], ...]) -> float:
        return configuration_fairness(
            [[skills[pid] for pid in team] for team in config]
        )

    top = _TopConfigurations(num_results)
    evaluated = 0

    if _partition_count(len(player_ids), sizes) <= EXHAUSTIVE_LIMIT:
        for config in _enumerate_partitions(player_ids, sizes):
            if not _satisfies_constraints(config, together, apart):
                continue
            top.offer(config, fairness_of(config))
            evaluated += 1
        ranked = top.best()
        if not ranked:
            raise InfeasibleConstraintsError(
                "No team configuration satisfies the given constraints"
            )
        return ranked, "exhaustive", evaluated

    # Simulated annealing with restarts
    rng = random.Random(seed)
    cfg = ANNEALING_CONFIG
    for _ in range(int(cfg["restarts"])):
        current = _random_valid_configuration(rng, player_ids, sizes, together, apart)
        if current is None:
            continue
        current_fairness = fairness_of(current)
        top.offer(current, current_fairness)
        evaluated += 1

        temperature = float(cfg["t_max"])
        while temperature > float(cfg["t_min"]):
            for _ in range(int(cfg["iterations_per_temp"])):
                candidate = _swap_players(rng, current)
                if not _satisfies_constraints(candidate, together, apart):
                    continue
                candidate_fairness = fairness_of(candidate)
                evaluated += 1
                delta = candidate_fairness - current_fairness
                if delta >= 0 or rng.random() < math.exp(delta / temperature):
                    current, current_fairness = candidate, candidate_fairness
                    top.offer(current, current_fairness)
            temperature *= float(cfg["cooling_rate"])

    ranked = top.best()
    if not ranked:
        raise InfeasibleConstraintsError(
            "No team configuration satisfying the constraints was found"
        )
    return ranked, "annealing", evaluated


# =============================================================================
# Service entry point
# =============================================================================


def _default_team_sizes(player_count: int, team_count: int) -> list[int]:
    """Split players as evenly as possible (larger teams first)."""
    base, extra = divmod(player_count, team_count)
    return [base + 1 if i < extra else base for i in range(team_count)]


def _validate_constraint_players(
    constraints: mm_schema.MatchmakingConstraints | None,
    player_ids: list[int],
    sizes: list[int],
) -> tuple[list[set[int]], list[set[int]]]:
    """Normalize constraints to sets and sanity-check feasibility."""
    if constraints is None:
        return [], []

    selected = set(player_ids)
    together = [set(group) for group in constraints.together if len(group) > 1]
    apart = [set(group) for group in constraints.apart if len(group) > 1]

    for group in together + apart:
        unknown = group - selected
        if unknown:
            raise InfeasibleConstraintsError(
                f"Constraint references players not in this session: {sorted(unknown)}"
            )

    max_team_size = max(sizes)
    for group in together:
        if len(group) > max_team_size:
            raise InfeasibleConstraintsError(
                f"A 'together' group of {len(group)} players cannot fit in "
                f"any team (largest team holds {max_team_size})"
            )

    for group in apart:
        if len(group) > len(sizes):
            raise InfeasibleConstraintsError(
                f"An 'apart' group of {len(group)} players cannot be spread "
                f"across {len(sizes)} teams"
            )

    return together, apart


async def generate_configurations(
    db: AsyncSession, request: mm_schema.MatchmakingRequest
) -> mm_schema.MatchmakingResponse:
    """Generate balanced team configurations for the requested players.

    Players without a profile for the game are treated as fresh
    (default rating), so brand-new players can be matched immediately.

    Raises:
        GameNotFoundError: If the game doesn't exist
        PlayerNotFoundError: If any player doesn't exist
        InfeasibleConstraintsError: If constraints rule out every partition
    """
    game = await db.get(models.Game, request.game_id)
    if game is None or game.deleted_at is not None:
        raise GameNotFoundError(request.game_id)

    # Load players and verify existence
    result = await db.execute(
        select(models.Player).where(models.Player.id.in_(request.player_ids))
    )
    players = {p.id: p for p in result.scalars().all()}
    for player_id in request.player_ids:
        player = players.get(player_id)
        if player is None or player.deleted_at is not None:
            raise PlayerNotFoundError(player_id)

    # Load profiles; absent profile = fresh player at the default rating
    profile_result = await db.execute(
        select(models.GameProfile).where(
            models.GameProfile.game_id == request.game_id,
            models.GameProfile.player_id.in_(request.player_ids),
            models.GameProfile.deleted_at.is_(None),
        )
    )
    profiles = {p.player_id: p for p in profile_result.scalars().all()}

    skills: dict[int, PlayerSkill] = {}
    for player_id in request.player_ids:
        profile = profiles.get(player_id)
        rating_info = profile.rating_info if profile else dict(DEFAULT_RATING_INFO)
        skills[player_id] = PlayerSkill(
            player_id=player_id,
            mu=float(rating_info["rating"]),
            sigma=float(rating_info["rd"]),
        )

    sizes = request.team_sizes or _default_team_sizes(
        len(request.player_ids), request.team_count
    )
    together, apart = _validate_constraint_players(
        request.constraints, request.player_ids, sizes
    )

    ranked, method, evaluated = search_configurations(
        skills,
        list(request.player_ids),
        sizes,
        request.num_results,
        together,
        apart,
        seed=request.seed,
    )

    logger.info(
        "Matchmaking complete",
        extra={
            "game_id": request.game_id,
            "player_count": len(request.player_ids),
            "method": method,
            "evaluated": evaluated,
            "best_fairness": ranked[0][0] if ranked else None,
        },
    )

    configurations = []
    for fairness, config in ranked:
        team_skills = [[skills[pid] for pid in team] for team in config]
        distributions = [team_distribution(team) for team in team_skills]

        win_probs = []
        for i, dist in enumerate(distributions):
            # P(this team outrates every other team), pairwise product
            p = 1.0
            for j, other in enumerate(distributions):
                if i != j:
                    p *= win_probability(dist, other)
            win_probs.append(round(p, 4))

        configurations.append(
            mm_schema.TeamConfiguration(
                teams=[
                    [
                        mm_schema.TeamMember(
                            player=PlayerRead.model_validate(players[pid]),
                            rating=skills[pid].mu,
                            rd=skills[pid].sigma,
                        )
                        for pid in team
                    ]
                    for team in config
                ],
                team_ratings=[
                    mm_schema.TeamRating(mu=round(mu, 2), sigma=round(sigma, 2))
                    for mu, sigma in distributions
                ],
                fairness=round(fairness, 4),
                win_probabilities=win_probs,
            )
        )

    return mm_schema.MatchmakingResponse(
        configurations=configurations,
        method=method,
        configurations_evaluated=evaluated,
    )
