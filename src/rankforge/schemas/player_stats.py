# src/rankforge/schemas/player_stats.py

"""Player statistics schemas."""

from pydantic import BaseModel, ConfigDict, Field

from .common import RatingInfo
from .game import GameRead


class GameStats(BaseModel):
    """Player statistics for a single game.

    Attributes:
        game: The game information
        rating_info: Current rating information
        matches_played: Total matches played
        wins: Total wins
        losses: Total losses
        draws: Total draws
        win_rate: Win percentage (0.0 - 1.0)
    """

    game: GameRead
    rating_info: RatingInfo
    matches_played: int = Field(0, ge=0)
    wins: int = Field(0, ge=0)
    losses: int = Field(0, ge=0)
    draws: int = Field(0, ge=0)
    win_rate: float = Field(0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(from_attributes=True)


class ChemistryEntry(BaseModel):
    """Aggregated record with (partner) or against (rival) one other player."""

    player_id: int
    player_name: str
    matches: int = Field(0, ge=0)
    wins: int = Field(0, ge=0)
    losses: int = Field(0, ge=0)
    draws: int = Field(0, ge=0)
    win_rate: float = Field(0.0, ge=0.0, le=1.0)


class PlayerChemistry(BaseModel):
    """Partner and head-to-head records for one player in one game.

    ``partners`` aggregates matches where the other player shared the
    player's team (win rate = how the duo fares together); ``rivals``
    aggregates matches on opposing teams (win rate = the player's record
    against that opponent).
    """

    player_id: int
    game_id: int
    partners: list[ChemistryEntry] = Field(default_factory=list)
    rivals: list[ChemistryEntry] = Field(default_factory=list)


class PlayerStats(BaseModel):
    """Aggregate statistics for a player across all games.

    Attributes:
        player_id: The player's ID
        player_name: The player's name
        total_matches: Total matches across all games
        total_wins: Total wins across all games
        total_losses: Total losses across all games
        total_draws: Total draws across all games
        overall_win_rate: Overall win percentage
        games_played: Per-game statistics
    """

    player_id: int
    player_name: str
    total_matches: int = Field(0, ge=0)
    total_wins: int = Field(0, ge=0)
    total_losses: int = Field(0, ge=0)
    total_draws: int = Field(0, ge=0)
    overall_win_rate: float = Field(0.0, ge=0.0, le=1.0)
    games_played: list[GameStats] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
