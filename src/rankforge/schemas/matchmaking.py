# src/rankforge/schemas/matchmaking.py

"""Pydantic schemas for the matchmaking endpoint."""

from pydantic import BaseModel, Field, model_validator

from .player import PlayerRead


class MatchmakingConstraints(BaseModel):
    """Optional constraints on team composition.

    together: groups of players that must end up on the same team.
    apart: groups of players that must NOT share a team (pairwise).
    """

    together: list[list[int]] = Field(default_factory=list)
    apart: list[list[int]] = Field(default_factory=list)


class MatchmakingRequest(BaseModel):
    """Request to generate balanced team configurations."""

    game_id: int
    player_ids: list[int] = Field(..., min_length=2, max_length=64)
    team_count: int = Field(default=2, ge=2)
    team_sizes: list[int] | None = Field(
        default=None,
        description=(
            "Explicit team sizes (must sum to len(player_ids)). "
            "Defaults to splitting players as evenly as possible."
        ),
    )
    num_results: int = Field(default=5, ge=1, le=20)
    constraints: MatchmakingConstraints | None = None
    seed: int | None = Field(
        default=None,
        description="Random seed for reproducible results (annealing only)",
    )
    recent_pairings: list[list[int]] | None = Field(
        default=None,
        description=(
            "Teammate groups from recent matches (e.g. this session's teams). "
            "Configurations that re-form these partnerships rank slightly "
            "lower, keeping session nights varied without sacrificing "
            "genuinely fairer matchups."
        ),
    )

    @model_validator(mode="after")
    def validate_request(self) -> "MatchmakingRequest":
        if len(set(self.player_ids)) != len(self.player_ids):
            raise ValueError("player_ids must be unique")
        if self.team_count > len(self.player_ids):
            raise ValueError("team_count cannot exceed the number of players")
        if self.team_sizes is not None:
            if len(self.team_sizes) != self.team_count:
                raise ValueError("team_sizes must have team_count entries")
            if any(size < 1 for size in self.team_sizes):
                raise ValueError("every team must have at least 1 player")
            if sum(self.team_sizes) != len(self.player_ids):
                raise ValueError("team_sizes must sum to the number of players")
        return self


class TeamRating(BaseModel):
    """A team's combined skill distribution N(mu, sigma)."""

    mu: float
    sigma: float


class TeamMember(BaseModel):
    """A player within a proposed team, with their current rating."""

    player: PlayerRead
    rating: float
    rd: float


class TeamConfiguration(BaseModel):
    """One proposed division of the players into teams."""

    teams: list[list[TeamMember]]
    team_ratings: list[TeamRating]
    fairness: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "1.0 = perfectly balanced (outcome is a coin flip); "
            "0.0 = completely one-sided"
        ),
    )
    win_probabilities: list[float] = Field(
        ...,
        description=(
            "Per-team probability of outrating every other team "
            "(pairwise product approximation)"
        ),
    )
    lopsided: bool = Field(
        default=False,
        description=(
            "True when the worst matchup gives one side more than 80% "
            "(fairness below 0.4) — playable, but flag it to the group"
        ),
    )


class MatchmakingResponse(BaseModel):
    """Ranked team configurations, most balanced first."""

    configurations: list[TeamConfiguration]
    method: str = Field(..., description="'exhaustive' or 'annealing'")
    configurations_evaluated: int
