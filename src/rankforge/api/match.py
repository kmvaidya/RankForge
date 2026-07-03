# src/rankforge/api/match.py

"""API endpoints for managing matches."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rankforge.db.models import Match, MatchParticipant
from rankforge.db.session import get_db
from rankforge.exceptions import (
    RatingEngineError,
    ResourceNotFoundError,
    ValidationError,
)
from rankforge.schemas import match as match_schema
from rankforge.schemas.pagination import MatchSortField, PaginatedResponse, SortOrder
from rankforge.services import match_service

# Create an APIRouter instance for matches
router = APIRouter(prefix="/matches", tags=["Matches"])


@router.get("/", response_model=PaginatedResponse[match_schema.MatchRead])
async def read_matches(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    sort_by: MatchSortField = Query(MatchSortField.PLAYED_AT, description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort direction"),
    game_id: int | None = Query(None, description="Filter by game ID"),
    player_id: int | None = Query(None, description="Filter by player"),
    played_after: datetime | None = Query(None, description="After this date"),
    played_before: datetime | None = Query(None, description="Before this date"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[match_schema.MatchRead]:
    """
    Retrieve a paginated list of matches with filtering options.

    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return (1-100)
    - **sort_by**: Field to sort by (id, played_at, created_at)
    - **sort_order**: Sort direction (asc, desc)
    - **game_id**: Filter by game ID
    - **player_id**: Filter by player participation
    - **played_after**: Filter matches played after this datetime
    - **played_before**: Filter matches played before this datetime
    """
    # Build base query with soft delete filter
    base_query = select(Match).where(Match.deleted_at.is_(None))

    # Apply filters
    if game_id is not None:
        base_query = base_query.where(Match.game_id == game_id)

    if player_id is not None:
        # Join with participants to filter by player
        base_query = base_query.join(MatchParticipant).where(
            MatchParticipant.player_id == player_id
        )

    if played_after is not None:
        base_query = base_query.where(Match.played_at >= played_after)

    if played_before is not None:
        base_query = base_query.where(Match.played_at <= played_before)

    # Get total count (need distinct when joining)
    count_subquery = base_query.subquery()
    if player_id is not None:
        count_query = select(
            func.count(func.distinct(count_subquery.c.id))
        ).select_from(count_subquery)
    else:
        count_query = select(func.count()).select_from(count_subquery)
    total = (await db.execute(count_query)).scalar_one()

    # Apply sorting
    sort_column = getattr(Match, sort_by.value)
    if sort_order == SortOrder.DESC:
        sort_column = sort_column.desc()

    # Apply pagination and eager load relationships
    query = (
        base_query.order_by(sort_column)
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


@router.post(
    "/", response_model=match_schema.MatchRead, status_code=status.HTTP_201_CREATED
)
async def create_match(
    match_in: match_schema.MatchCreate, db: AsyncSession = Depends(get_db)
) -> Match:
    """
    Create a new match, process ratings, and return the created match.

    Participants can specify:
    - player_id: Reference to an existing player
    - player_id=None: Create an anonymous player for this match

    Raises:
        404: If game_id or player_id doesn't exist
        422: If validation fails (< 2 participants, duplicates, < 2 teams)
        500: If rating calculation fails
    """
    try:
        created_match = await match_service.process_new_match(db, match_in)
        return created_match

    except ResourceNotFoundError as e:
        # GameNotFoundError, PlayerNotFoundError -> 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        )

    except ValidationError as e:
        # ParticipantValidationError variants -> 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.message,
        )

    except RatingEngineError:
        # Rating calculation failures -> 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rating calculation failed. Please try again.",
        )


@router.get("/{match_id}", response_model=match_schema.MatchRead)
async def read_match(match_id: int, db: AsyncSession = Depends(get_db)) -> Match:
    """
    Retrieve a single match by its ID, including its participants and their players.
    """
    # 1. Build a query to select the Match.
    # 2. Use `options` and `selectinload` to create an efficient query that
    #    "eager loads" the related participants and their nested player objects.
    #    This prevents the "N+1 problem" by issuing just two extra queries
    #    (one for all participants, one for all players) instead of one per participant.
    query = (
        select(Match)
        .where(Match.id == match_id)
        .options(selectinload(Match.participants).selectinload(MatchParticipant.player))
    )

    result = await db.execute(query)
    match = result.scalar_one_or_none()

    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Match with id {match_id} not found",
        )

    return match


@router.delete("/{match_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_match(match_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """
    Delete a match by its ID.
    """
    # Fetch the match to delete
    match_to_delete = await db.get(Match, match_id)
    if not match_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Match with id {match_id} not found",
        )

    # Delete from the database. Thanks to `cascade="all, delete-orphan"` in our
    # `models.py` relationship, SQLAlchemy will automatically delete all
    # associated MatchParticipant records as well.
    await db.delete(match_to_delete)
    await db.commit()

    return None
