# src/rankforge/main.py

"""Main FastAPI application for RankForge."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .api import game, match, matchmaking, player
from .db.session import engine
from .exceptions import (
    ConflictError,
    RankForgeError,
    RatingEngineError,
    ResourceNotFoundError,
    ValidationError,
)
from .middleware.logging import RequestLoggingMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events."""
    # Startup: Nothing special needed, engine is created on import
    yield
    # Shutdown: Dispose of database connections gracefully
    await engine.dispose()


app = FastAPI(title="RankForge API", lifespan=lifespan)

# Add middleware (order matters - first added = outermost)
app.add_middleware(RequestLoggingMiddleware)


# =============================================================================
# Global Exception Handlers
# =============================================================================


@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_handler(
    request: Request, exc: ResourceNotFoundError
) -> JSONResponse:
    """Handle all resource not found errors -> 404."""
    logger.warning("Resource not found: %s", exc.message, extra=exc.details)
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message, "error_type": type(exc).__name__},
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Handle all validation errors -> 422."""
    logger.warning("Validation error: %s", exc.message, extra=exc.details)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.message, "error_type": type(exc).__name__},
    )


@app.exception_handler(ConflictError)
async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
    """Handle conflict errors (e.g., concurrent modification) -> 409."""
    logger.warning("Conflict: %s", exc.message, extra=exc.details)
    return JSONResponse(
        status_code=409,
        content={"detail": exc.message, "error_type": type(exc).__name__},
    )


@app.exception_handler(RatingEngineError)
async def rating_engine_error_handler(
    request: Request, exc: RatingEngineError
) -> JSONResponse:
    """Handle rating engine errors -> 500."""
    logger.error(
        "Rating engine error: %s", exc.message, extra=exc.details, exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Rating calculation failed",
            "error_type": type(exc).__name__,
        },
    )


@app.exception_handler(RankForgeError)
async def rankforge_error_handler(
    request: Request, exc: RankForgeError
) -> JSONResponse:
    """Catch-all for any other RankForge errors -> 500."""
    logger.error("RankForge error: %s", exc.message, extra=exc.details, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": exc.message, "error_type": type(exc).__name__},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    """Handle database integrity constraint violations."""
    error_msg = str(exc.orig) if exc.orig else str(exc)
    logger.warning("Database integrity error: %s", error_msg)

    # Unique constraint violations -> 409 Conflict
    if "UNIQUE constraint failed" in error_msg or "duplicate key" in error_msg:
        return JSONResponse(
            status_code=409,
            content={"detail": "Resource already exists with given unique field(s)"},
        )

    # Foreign key violations -> 400 Bad Request
    fk_error = "FOREIGN KEY constraint failed" in error_msg
    if fk_error or "violates foreign key" in error_msg:
        return JSONResponse(
            status_code=400,
            content={"detail": "Referenced resource does not exist"},
        )

    # Fallback for other integrity errors
    return JSONResponse(
        status_code=400,
        content={"detail": "Database constraint violation"},
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """Catch-all for other SQLAlchemy database errors."""
    logger.error("Database error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal database error occurred"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred"},
    )


# Include routers into the main application
app.include_router(game.router)
app.include_router(player.router)
app.include_router(match.router)
app.include_router(matchmaking.router)


@app.get("/", tags=["Root"])
async def read_root() -> dict[str, str]:
    """Provides a welcome message."""
    return {"message": "Welcome to the RankForge API"}


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}
