# src/rankforge/schemas/prediction.py

"""Match-prediction and rating-calibration schemas."""

from pydantic import BaseModel, Field, field_validator


class PredictionRequest(BaseModel):
    """A hypothetical team split to predict: two or more teams of player ids."""

    teams: list[list[int]] = Field(..., min_length=2)

    @field_validator("teams")
    @classmethod
    def validate_teams(cls, teams: list[list[int]]) -> list[list[int]]:
        if any(len(team) == 0 for team in teams):
            raise ValueError("every team needs at least one player")
        flat = [pid for team in teams for pid in team]
        if len(flat) != len(set(flat)):
            raise ValueError("a player cannot appear on more than one team")
        return teams


class TeamPrediction(BaseModel):
    """One team's side of a prediction."""

    player_ids: list[int]
    rating: float
    rd: float
    expected_score: float = Field(..., ge=0.0, le=1.0)
    win_probability: float = Field(..., ge=0.0, le=1.0)


class PredictionResponse(BaseModel):
    """Win probabilities for a team split, from the rating engine's own math.

    ``expected_score`` is the mean Glicko-2 expected outcome of the team's
    members against every opponent; ``win_probability`` normalizes those
    scores across teams so they sum to 1.
    """

    game_id: int
    teams: list[TeamPrediction]
    favored_team_index: int
    lopsided: bool
    method: str = "glicko2_expected_score"


class CalibrationBin(BaseModel):
    """One reliability-diagram bin: predicted probability vs observed rate."""

    lower: float
    upper: float
    count: int
    mean_predicted: float | None = None
    actual_rate: float | None = None


class CalibrationReport(BaseModel):
    """Walk-forward (predict-before-update) evaluation of a game's ratings.

    Every prediction is made strictly from ratings as they stood before the
    match being scored, then the match is applied — the same leakage-free
    protocol used to validate the engine offline. ``brier`` is the mean
    squared error of the predictions (0.25 = coin flips, lower is better),
    ``ece`` the 10-bin expected calibration error, and
    ``rating_winrate_spearman`` the rank correlation between final ratings
    and observed mean scores for established players.
    """

    game_id: int
    matches_replayed: int
    comparisons_evaluated: int
    warmup: int
    brier: float | None = None
    accuracy: float | None = None
    ece: float | None = None
    bins: list[CalibrationBin] = Field(default_factory=list)
    rating_winrate_spearman: float | None = None
    spearman_players: int = 0
