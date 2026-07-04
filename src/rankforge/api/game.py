# src/rankforge/api/game.py

"""API endpoints for managing games."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rankforge.db.models import Game, GameProfile, Match, Player
from rankforge.db.session import get_db
from rankforge.schemas import game as game_schema
from rankforge.schemas.common import RatingInfo
from rankforge.schemas.leaderboard import LeaderboardEntry
from rankforge.schemas.match import RecalculationResult
from rankforge.schemas.pagination import GameSortField, PaginatedResponse, SortOrder
from rankforge.services import recalculation_service, season_service

# Creates an APIRouter instance
# - prefix="/games": All routes defined here will be prefixed with /games
# - tags=["Games"]: Groups these endpoints under "Games" in the API docs
router = APIRouter(prefix="/games", tags=["Games"])


@router.post(
    "/",
    response_model=game_schema.GameRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_game(
    game_in: game_schema.GameCreate,
    db: AsyncSession = Depends(get_db),
) -> Game:
    """
    Create a new game.

    - **name**: The unique name of the game.
    - **rating_strategy**: The identifier for the rating calculation engine.
    - **description**: An optional description of the game.

    Raises:
        409 Conflict: If a game with the same name already exists.
    """
    # Create a new SQLAlchemy Game model instance from the Pydantic schema data
    new_game = Game(**game_in.model_dump())

    # Add the new instance to the database session, commit and refresh
    try:
        db.add(new_game)
        await db.commit()
        await db.refresh(new_game)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Game with name '{game_in.name}' already exists",
        )

    return new_game


@router.get("/", response_model=PaginatedResponse[game_schema.GameRead])
async def read_games(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    sort_by: GameSortField = Query(GameSortField.ID, description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[game_schema.GameRead]:
    """
    Retrieve a paginated list of games.

    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return (1-100)
    - **sort_by**: Field to sort by (id, name, created_at)
    - **sort_order**: Sort direction (asc, desc)
    """
    # Build base query with soft delete filter
    base_query = select(Game).where(Game.deleted_at.is_(None))

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Apply sorting
    sort_column = getattr(Game, sort_by.value)
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


@router.get("/{game_id}", response_model=game_schema.GameRead)
async def read_game(game_id: int, db: AsyncSession = Depends(get_db)) -> Game:
    """
    Retrieve a single game by its ID.
    """
    # 1. Execute a query to find the game by its primary key.
    game = await db.get(Game, game_id)

    # 2. If the game is not found, `game` will be `None`, and will raise 404 Error.
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with id {game_id} not found",
        )

    # 3. If the game is found, return it.
    return game


@router.put("/{game_id}", response_model=game_schema.GameRead)
async def update_game(
    game_id: int,
    game_in: game_schema.GameUpdate,
    db: AsyncSession = Depends(get_db),
) -> Game:
    """
    Update a game by its ID.

    Raises:
        404 Not Found: If the game doesn't exist.
        409 Conflict: If the new name conflicts with an existing game.
    """
    # Fetch the desired game to update.
    game_to_update = await db.get(Game, game_id)
    if not game_to_update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with id {game_id} not found",
        )

    # Get the update data, excluding fields that were not sent.
    update_data = game_in.model_dump(exclude_unset=True)

    # Update the model instance with the new data
    for key, value in update_data.items():
        setattr(game_to_update, key, value)

    # Add, commit, and refresh
    try:
        db.add(game_to_update)
        await db.commit()
        await db.refresh(game_to_update)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Game with name '{game_in.name}' already exists",
        )

    return game_to_update


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(game_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """
    Delete a game by its ID.
    """
    # 1. Fetch the desired game to delete.
    game_to_delete = await db.get(Game, game_id)
    if not game_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with id {game_id} not found",
        )

    # 2. Delete the object from the database, and commit.
    await db.delete(game_to_delete)
    await db.commit()

    # 4. A 204 response has no body, sso return None.
    return None


@router.get(
    "/{game_id}/leaderboard",
    response_model=PaginatedResponse[LeaderboardEntry],
)
async def get_leaderboard(
    game_id: int,
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    include_anonymous: bool = Query(False, description="Include anonymous"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[LeaderboardEntry]:
    """
    Get player rankings for a specific game.

    Returns players ranked by rating (highest first) with their stats.

    - **game_id**: The ID of the game to get leaderboard for
    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return (1-100)
    - **include_anonymous**: Whether to include anonymous players (default: false)
    """
    # Verify game exists
    game = await db.get(Game, game_id)
    if not game or game.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with id {game_id} not found",
        )

    # Build query for GameProfiles with player data
    base_query = (
        select(GameProfile)
        .where(GameProfile.game_id == game_id)
        .where(GameProfile.deleted_at.is_(None))
        .join(Player)
        .where(Player.deleted_at.is_(None))
        .options(selectinload(GameProfile.player))
    )

    # Filter anonymous players unless explicitly requested
    if not include_anonymous:
        base_query = base_query.where(Player.is_anonymous == False)  # noqa: E712

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Execute query with pagination
    # Note: Sorting by rating in JSON field requires database-specific handling.
    # For now, we fetch all and sort in Python, then paginate.
    # For large datasets, consider extracting rating to a dedicated column.
    query = base_query.options(selectinload(GameProfile.player))
    result = await db.execute(query)
    all_profiles = list(result.scalars().unique().all())

    # Sort by rating (descending) - higher rating = better rank
    all_profiles.sort(
        key=lambda p: p.rating_info.get("rating", 0) if p.rating_info else 0,
        reverse=True,
    )

    # Apply pagination
    paginated_profiles = all_profiles[skip : skip + limit]

    # Build leaderboard entries with ranks
    entries = [
        LeaderboardEntry(
            rank=skip + i + 1,
            player=profile.player,  # type: ignore[arg-type]
            rating_info=RatingInfo(
                rating=profile.rating_info.get("rating", 1500.0),
                rd=profile.rating_info.get("rd", 350.0),
                vol=profile.rating_info.get("vol", 0.06),
            ),
            stats=profile.stats or {},
        )
        for i, profile in enumerate(paginated_profiles)
    ]

    return PaginatedResponse(
        items=entries,
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + len(entries)) < total,
    )


@router.get("/{game_id}/health", response_model=game_schema.GameHealth)
async def get_game_health(
    game_id: int, db: AsyncSession = Depends(get_db)
) -> game_schema.GameHealth:
    """
    Rating-system health for a game: mean rating and drift from the 1500
    anchor. Sustained drift signals inflation/deflation. Anonymous players
    are excluded, matching the leaderboard.
    """
    game = await db.get(Game, game_id)
    if not game or game.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with id {game_id} not found",
        )

    profiles_query = (
        select(GameProfile.rating_info)
        .where(GameProfile.game_id == game_id)
        .where(GameProfile.deleted_at.is_(None))
        .join(Player, Player.id == GameProfile.player_id)
        .where(Player.deleted_at.is_(None))
        .where(Player.is_anonymous == False)  # noqa: E712
    )
    ratings = [
        info.get("rating", 1500.0)
        for info in (await db.execute(profiles_query)).scalars().all()
    ]

    match_count_query = (
        select(func.count())
        .select_from(Match)
        .where(Match.game_id == game_id)
        .where(Match.deleted_at.is_(None))
    )
    matches = (await db.execute(match_count_query)).scalar_one()

    mean = sum(ratings) / len(ratings) if ratings else 1500.0
    return game_schema.GameHealth(
        game_id=game_id,
        players=len(ratings),
        matches=matches,
        mean_rating=round(mean, 2),
        rating_drift=round(abs(1500.0 - mean), 2),
    )


@router.get("/{game_id}/seasons", response_model=game_schema.SeasonList)
async def get_seasons(
    game_id: int, db: AsyncSession = Depends(get_db)
) -> game_schema.SeasonList:
    """
    A game's season boundaries. Season 1 is implicit; the current season is
    1 until the first boundary is created.
    """
    game = await db.get(Game, game_id)
    if not game or game.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with id {game_id} not found",
        )
    seasons = await season_service.list_seasons(db, game_id)
    current = await season_service.current_season_number(db, game_id)
    return game_schema.SeasonList(
        current_season=current,
        items=[game_schema.SeasonRead.model_validate(s) for s in seasons],
    )


@router.post(
    "/{game_id}/seasons",
    response_model=game_schema.SeasonRead,
    status_code=status.HTTP_201_CREATED,
)
async def start_season(
    game_id: int, db: AsyncSession = Depends(get_db)
) -> game_schema.SeasonRead:
    """
    Start a new season: every profile's RD resets to
    rating_config.season_rd_reset (default 350) so the ladder re-opens,
    ratings and volatility persist, and per-season stats zero out.
    """
    season = await season_service.start_season(db, game_id)
    return game_schema.SeasonRead(
        id=season.id,
        game_id=season.game_id,
        number=season.number,
        started_at=season.started_at,
    )


@router.post("/{game_id}/recalculate", response_model=RecalculationResult)
async def recalculate_game(
    game_id: int, db: AsyncSession = Depends(get_db)
) -> RecalculationResult:
    """
    Rebuild a game's entire rating history and stats from scratch.

    Maintenance operation: replays every non-deleted match in chronological
    order. Useful after bulk imports or to heal data recorded before stats
    tracking existed.

    Raises:
        404: If the game doesn't exist
    """
    stats = await recalculation_service.recalculate_game(db, game_id)
    return RecalculationResult(
        matches_recalculated=stats.matches_recalculated,
        players_affected=stats.players_affected,
    )
