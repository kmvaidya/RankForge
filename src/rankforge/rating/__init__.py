# src/rankforge/rating/__init__.py

"""Rating engine registry and dispatch.

Each engine module exposes an async ``update_ratings_for_match(db, match)``
function that recalculates ratings for a single match, flushing (never
committing) so the caller owns the transaction boundary.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from rankforge.db import models
from rankforge.rating import dummy_engine, glicko2_engine

RatingEngineFn = Callable[[AsyncSession, models.Match], Awaitable[None]]

# Maps Game.rating_strategy values to engine modules. Resolution happens at
# dispatch time (module attribute lookup) so tests can patch an engine's
# update_ratings_for_match.
ENGINE_MODULES = {
    "glicko2": glicko2_engine,
    "dummy": dummy_engine,
}


def get_rating_engine(strategy: str) -> RatingEngineFn:
    """Return the rating engine for a strategy, defaulting to the dummy engine."""
    module = ENGINE_MODULES.get(strategy, dummy_engine)
    fn: RatingEngineFn = module.update_ratings_for_match
    return fn
