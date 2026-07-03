# src/rankforge/api/matchmaking.py

"""API endpoint for generating balanced team configurations."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rankforge.db.session import get_db
from rankforge.schemas import matchmaking as mm_schema
from rankforge.services import matchmaking_service

router = APIRouter(prefix="/matchmaking", tags=["Matchmaking"])


@router.post("/generate", response_model=mm_schema.MatchmakingResponse)
async def generate_teams(
    request: mm_schema.MatchmakingRequest,
    db: AsyncSession = Depends(get_db),
) -> mm_schema.MatchmakingResponse:
    """
    Generate balanced team configurations for a set of players.

    Models each player's skill as a Gaussian from their Glicko-2 rating
    (mean) and rating deviation (uncertainty), superposes them into team
    distributions, and searches for partitions where the outcome is closest
    to a coin flip. Small player counts are solved exhaustively; larger ones
    use simulated annealing.

    Constraints: `together` groups must share a team; `apart` groups must
    all land on different teams.

    Raises:
        404: If the game or any player doesn't exist
        422: If the request is invalid or constraints are infeasible
    """
    return await matchmaking_service.generate_configurations(db, request)
