# src/rankforge/api/player.py

"""API endpoints for managing players."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rankforge.db.models import GameProfile, Match, MatchParticipant, Player
from rankforge.db.session import get_db
from rankforge.schemas import match as match_schema
from rankforge.schemas import player as player_schema
from rankforge.schemas.common import RatingInfo
from rankforge.schemas.pagination import PaginatedResponse, PlayerSortField, SortOrder
from rankforge.schemas.player_stats import GameStats, PlayerStats

# Create an APIRouter instance for players
# - prefix="/players": All routes here will be prefixed with /players
# - tags=["Players"]: Groups these endpoints under "Players" in the API docs
router = APIRouter(prefix="/players", tags=["Players"])


@router.post(
    "/",
    response_model=player_schema.PlayerRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_player(
    player_in: player_schema.PlayerCreate, db: AsyncSession = Depends(get_db)
) -> Player:
    """
    Create a new player.

    - **name**: The unique name for the player.

    Raises:
        409 Conflict: If a player with the same name already exists.
    """
    # Create a new SQLAlchemy Player model instance
    new_player = Player(**player_in.model_dump())

    # Add, commit, and refresh to save to the database and get the new ID
    try:
        db.add(new_player)
        await db.commit()
        await db.refresh(new_player)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Player with name '{player_in.name}' already exists",
        )

    # Return the newly created player object
    return new_player


@router.get("/", response_model=PaginatedResponse[player_schema.PlayerRead])
async def read_players(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    sort_by: PlayerSortField = Query(PlayerSortField.ID, description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    include_anonymous: bool = Query(False, description="Include anonymous"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[player_schema.PlayerRead]:
    """
    Retrieve a paginated list of players.

    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return (1-100)
    - **sort_by**: Field to sort by (id, name, created_at)
    - **sort_order**: Sort direction (asc, desc)
    - **include_anonymous**: Whether to include anonymous players (default: false)
    """
    # Build base query with soft delete filter
    base_query = select(Player).where(Player.deleted_at.is_(None))

    # Filter anonymous players unless explicitly requested
    if not include_anonymous:
        base_query = base_query.where(Player.is_anonymous == False)  # noqa: E712

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Apply sorting
    sort_column = getattr(Player, sort_by.value)
    if sort_order == SortOrder.DESC:
        sort_column = sort_column.desc()

    # Apply pagination
    query = base_query.order_by(sort_column).offset(skip).limit(limit)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return PaginatedResponse(
        items=items,  # type: ignore[arg-type]
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + len(items)) < total,
    )


@router.get("/{player_id}", response_model=player_schema.PlayerRead)
async def read_player(player_id: int, db: AsyncSession = Depends(get_db)) -> Player:
    """
    Retrieve a single player by their ID.
    """
    # Fetch player by Primary Key
    player = await db.get(Player, player_id)

    # If not found, raise a standard 404 error
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with id {player_id} not found",
        )

    # Return the found player object
    return player


@router.put("/{player_id}", response_model=player_schema.PlayerRead)
async def update_player(
    player_id: int,
    player_in: player_schema.PlayerUpdate,
    db: AsyncSession = Depends(get_db),
) -> Player:
    """
    Update a player's name.

    Raises:
        404 Not Found: If the player doesn't exist.
        409 Conflict: If the new name conflicts with an existing player.
    """
    # Fetch the existing player
    player_to_update = await db.get(Player, player_id)
    if not player_to_update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with id {player_id} not found",
        )

    # Get the update data, excluding fields that were not sent
    update_data = player_in.model_dump(exclude_unset=True)

    # Update the model instance with the new data
    for key, value in update_data.items():
        setattr(player_to_update, key, value)

    # Add, commit, and refresh
    try:
        db.add(player_to_update)
        await db.commit()
        await db.refresh(player_to_update)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Player with name '{player_in.name}' already exists",
        )

    return player_to_update


@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(player_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """
    Delete a player by their ID.
    """
    # Fetch the player to delete
    player_to_delete = await db.get(Player, player_id)
    if not player_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with id {player_id} not found",
        )

    # Delete from the database
    await db.delete(player_to_delete)
    await db.commit()

    # Return None for the 204 No Content response
    return None


@router.get("/{player_id}/stats", response_model=PlayerStats)
async def get_player_stats(
    player_id: int,
    db: AsyncSession = Depends(get_db),
) -> PlayerStats:
    """
    Get aggregate statistics for a player across all games.

    Returns overall stats and per-game breakdown of rating, wins, losses, etc.
    """
    # Verify player exists
    player = await db.get(Player, player_id)
    if not player or player.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with id {player_id} not found",
        )

    # Get all game profiles for this player with game data
    query = (
        select(GameProfile)
        .where(GameProfile.player_id == player_id)
        .where(GameProfile.deleted_at.is_(None))
        .options(selectinload(GameProfile.game))
    )
    result = await db.execute(query)
    profiles = list(result.scalars().all())

    # Calculate per-game stats and aggregate totals
    game_stats_list = []
    total_matches = 0
    total_wins = 0
    total_losses = 0
    total_draws = 0

    for profile in profiles:
        stats = profile.stats or {}
        matches = stats.get("matches_played", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        draws = stats.get("draws", 0)

        game_stats_list.append(
            GameStats(
                game=profile.game,  # type: ignore[arg-type]
                rating_info=RatingInfo(
                    rating=profile.rating_info.get("rating", 1500.0),
                    rd=profile.rating_info.get("rd", 350.0),
                    vol=profile.rating_info.get("vol", 0.06),
                ),
                matches_played=matches,
                wins=wins,
                losses=losses,
                draws=draws,
                win_rate=wins / matches if matches > 0 else 0.0,
            )
        )

        total_matches += matches
        total_wins += wins
        total_losses += losses
        total_draws += draws

    return PlayerStats(
        player_id=player.id,
        player_name=player.name,
        total_matches=total_matches,
        total_wins=total_wins,
        total_losses=total_losses,
        total_draws=total_draws,
        overall_win_rate=total_wins / total_matches if total_matches > 0 else 0.0,
        games_played=game_stats_list,
    )


@router.get(
    "/{player_id}/matches",
    response_model=PaginatedResponse[match_schema.MatchRead],
)
async def get_player_matches(
    player_id: int,
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    game_id: int | None = Query(None, description="Filter by game ID"),
    played_after: datetime | None = Query(None, description="After this date"),
    played_before: datetime | None = Query(None, description="Before this date"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort by played_at"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[match_schema.MatchRead]:
    """
    Get match history for a specific player.

    - **player_id**: The ID of the player
    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return (1-100)
    - **game_id**: Filter by game ID
    - **played_after**: Filter matches played after this datetime
    - **played_before**: Filter matches played before this datetime
    - **sort_order**: Sort direction for played_at (asc, desc)
    """
    # Verify player exists
    player = await db.get(Player, player_id)
    if not player or player.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with id {player_id} not found",
        )

    # Build base query - matches where this player participated
    base_query = (
        select(Match)
        .join(MatchParticipant)
        .where(MatchParticipant.player_id == player_id)
        .where(Match.deleted_at.is_(None))
    )

    # Apply filters
    if game_id is not None:
        base_query = base_query.where(Match.game_id == game_id)

    if played_after is not None:
        base_query = base_query.where(Match.played_at >= played_after)

    if played_before is not None:
        base_query = base_query.where(Match.played_at <= played_before)

    # Get total count (distinct because of join)
    count_subquery = base_query.subquery()
    count_query = select(func.count(func.distinct(count_subquery.c.id))).select_from(
        count_subquery
    )
    total = (await db.execute(count_query)).scalar_one()

    # Apply sorting
    if sort_order == SortOrder.DESC:
        order_col = Match.played_at.desc()
    else:
        order_col = Match.played_at.asc()

    # Apply pagination and eager load relationships
    query = (
        base_query.order_by(order_col)
        .offset(skip)
        .limit(limit)
        .options(selectinload(Match.participants).selectinload(MatchParticipant.player))
    )
    result = await db.execute(query)
    items = list(result.scalars().unique().all())

    return PaginatedResponse(
        items=items,  # type: ignore[arg-type]
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + len(items)) < total,
    )
