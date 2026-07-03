# Project Master Plan: RankForge - Competitive Gaming Analytics Platform

## Executive Summary

RankForge is a modern, game-agnostic rating and matchmaking system designed to track player performance across any competitive format (1v1, 1vN, MvN). The project serves dual purposes: providing a fun, competitive experience for tracking performance among friends, and functioning as a portfolio showcase demonstrating expertise across mathematics, data science, software development, and frontend skills.

The project has a **functional but not production-ready backend** with a working FastAPI application, complete Glicko-2 rating implementation, and flexible data models. However, a deep code analysis reveals **significant technical debt and architectural issues** that must be addressed before building on this foundation. Critical problems include: broken transaction management that can leave matches and ratings in inconsistent states, missing database indexes, unvalidated JSON schemas, hardcoded configuration, and incomplete error handling. The codebase scores approximately **4.5/10 on production readiness**.

Beyond code quality, the project is missing critical components: **no frontend exists**, **no matchmaking algorithm is implemented**, **no leaderboard/analytics endpoints are available**, and match update operations (a core challenge) have no implementation or design. The update cascade problem—recalculating all affected ratings when a historical match is corrected—is a non-trivial architectural challenge that requires careful design.

The path to MVP completion requires approximately **309-348 hours of development** across five major phases: foundation refactoring (Phase 0), matchmaking and match updates (Phase 1), frontend development (Phase 2), deployment (Phase 3), and documentation (Phase 4). At 3-6 hours per week, this translates to roughly **18-24 months** of dedicated work. Phase 0 is significantly expanded (122 hours) to establish a truly production-quality foundation before adding new features.

---

## Current State Assessment

### What's Implemented

**Backend Infrastructure (Functional, Not Production-Ready)**
- FastAPI async web application with automatic OpenAPI documentation
- SQLAlchemy 2.0 ORM with async support (aiosqlite for development)
- Alembic database migrations for schema versioning
- Basic separation of concerns: API routes, schemas, services, models
- *Note: See "Critical Code Quality Issues" section for production-readiness gaps*

**Data Models (Complete)**
- `Player` - Unique person across all games
- `Game` - Defines competitive game structure with pluggable rating strategy
- `GameProfile` - Player's rating and stats for a specific game (flexible JSON fields)
- `Match` - Single instance of a game with contextual metadata
- `MatchParticipant` - Links players to matches with outcomes and rating history

**API Endpoints (13 Endpoints)**
- Players: Full CRUD (POST, GET list, GET single, PUT, DELETE)
- Games: Full CRUD (POST, GET list, GET single, PUT, DELETE)
- Matches: Create, Read list, Read single, Delete

**Rating System**
- Complete Glicko-2 implementation ([glicko2_engine.py](src/rankforge/rating/glicko2_engine.py))
- Based on Mark Glickman's paper with proper mathematical implementation
- Supports binary (win/loss) and ranked outcomes
- Team-based calculations with proper opponent aggregation
- Historical rating tracking (before/after each match)

**Code Quality Infrastructure**
- Pre-commit hooks with Ruff (linting/formatting) and Mypy (type checking)
- Comprehensive test suite (~1,200 lines across 7 test modules)
- Async-first testing with pytest-asyncio
- In-memory test database with transactional isolation

**Data Import System**
- 24+ data import scripts for real-world match history (Pickleball, Tennis, Padel)
- Demonstrates API usage patterns and real data structures

### What's In Progress

- **Rating Strategy Dispatcher**: Architecture exists for multiple rating engines; currently routes to Glicko-2 or dummy engine based on game's `rating_strategy` field
- **Match History Tracking**: Basic structure in place (rating_info_before, rating_info_change), but no dedicated history retrieval endpoints

### What's Missing

**Core Features Needed for MVP**
1. **Leaderboard/Rankings Endpoints** - No endpoints to retrieve sorted player rankings by game
2. **Player Statistics Endpoints** - No endpoints for win/loss records, match history per player
3. **Game Profile Retrieval** - No endpoints to get all players' ratings for a specific game
4. **Matchmaking System** - Zero implementation; this is the novel algorithm (distribution superposition + simulated annealing)
5. **Frontend Application** - No frontend code exists whatsoever
6. **User Authentication** - No auth system (acceptable for friends-only use, but needed for public deployment)

**Infrastructure Gaps**
1. **No production deployment configuration** - No Dockerfile, docker-compose, or cloud deployment manifests
2. **No environment configuration** - Empty `.env` file, hardcoded SQLite database path
3. **No API rate limiting or security hardening**
4. **No monitoring, logging, or health check endpoints**

**Documentation/Testing Gaps**
1. **No API usage examples** - README covers setup but not how to use the API
2. **No architecture documentation** - No diagrams or detailed system explanations
3. **No user guide** - No documentation for end users
4. **Limited integration tests** - Most tests are unit/service level, fewer end-to-end API tests

### Technical Debt & Refactoring Needs

1. **Import Scripts Cleanup** - 24 versions of pickleball import script should be consolidated into a single configurable importer
2. **Database URL Hardcoding** - Currently hardcoded in [session.py](src/rankforge/db/session.py); should use environment variables
3. **Error Handling Consistency** - Some edge cases (e.g., non-competitive matches) have TODO comments rather than proper error handling
4. **Pydantic Schema Expansion** - Current schemas don't expose rating info in player responses; need GameProfile schemas for leaderboard use
5. **Type Annotations** - Some function parameters lack full type hints
6. **Test Coverage for Glicko-2** - Mathematical edge cases (very high/low RD, extreme rating differences) need more test coverage

---

## Critical Code Quality Issues

This section provides a thorough analysis of production-readiness gaps that must be addressed in Phase 0. The codebase currently scores approximately **4.5/10** on production readiness.

### Production Readiness Summary

| Component | Score | Status |
|-----------|-------|--------|
| Database Models | 6/10 | NEEDS WORK |
| Session Management | 3/10 | CRITICAL |
| Pydantic Schemas | 5/10 | NEEDS WORK |
| Service Layer | 4/10 | CRITICAL |
| API Layer | 5/10 | NEEDS WORK |
| Test Coverage | 4/10 | INCOMPLETE |

### Database Models Issues

**Schema Design Problems:**

1. **Missing Timestamp Tracking** - `GameProfile`, `Match`, and `MatchParticipant` lack `created_at` and `updated_at` fields, making audit trails impossible for rating investigations.

2. **No Database Indexes** - No explicit indexes beyond primary/unique constraints. Queries filtering by `player_id`, `game_id`, `match_id` will perform full table scans at scale.
   ```python
   # Missing indexes needed on:
   # - GameProfile.player_id, GameProfile.game_id
   # - MatchParticipant.match_id, MatchParticipant.player_id
   # - Match.game_id
   ```

3. **Unvalidated JSON Fields** - `rating_info`, `stats`, `outcome`, and `match_metadata` accept any dict without structure validation. No TypedDict or schema enforcement.

4. **Rating Key Inconsistency** - The codebase uses inconsistent keys:
   - `glicko2_engine.py`: `rating`, `rd`, `vol`
   - Schema comments: `rating`, `rd`, `volatility`
   - This causes hidden bugs in rating updates.

5. **Inconsistent Cascade Behavior** - `Player.game_profiles` cascades on delete, but `Player.match_participations` does not, leaving orphaned records.

6. **No Soft Delete Support** - Hard deletes destroy match history integrity. No `deleted_at` field for any model.

### Session Management Issues (CRITICAL)

1. **Hardcoded Database URL:**
   ```python
   # Current (session.py)
   DATABASE_URL = "sqlite+aiosqlite:///./rankforge.db"

   # Should be:
   DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./rankforge.db")
   ```

2. **No Connection Pool Configuration:**
   ```python
   # Current
   engine = create_async_engine(DATABASE_URL)

   # Should be:
   engine = create_async_engine(
       DATABASE_URL,
       pool_size=20,
       max_overflow=10,
       pool_pre_ping=True,
   )
   ```

3. **Dangerous `expire_on_commit=False`** - Objects remain accessible after commit but may contain stale data.

4. **No Connection Lifecycle Management** - No disposal on shutdown, no graceful cleanup.

5. **Missing Error Handling in `get_db()`** - No try-except with explicit rollback on failure.

### Pydantic Schema Issues

1. **No Field Validation:**
   ```python
   # Current
   class PlayerCreate(PlayerBase):
       pass  # No validation

   # Should be:
   class PlayerCreate(PlayerBase):
       name: str = Field(..., min_length=2, max_length=100)
   ```

2. **Untyped `outcome` Field:**
   ```python
   # Current
   outcome: dict  # Accepts anything

   # Should be:
   class BinaryOutcome(BaseModel):
       result: Literal["win", "loss", "draw"]

   class RankedOutcome(BaseModel):
       rank: int = Field(..., ge=1)
   ```

3. **No `rating_strategy` Enum:**
   ```python
   # Should validate against implemented strategies:
   class RatingStrategy(str, Enum):
       GLICKO2 = "glicko2"
       DUMMY = "dummy"
   ```

4. **Missing Fields in Read Schemas** - `MatchParticipantRead` doesn't include `rating_info_before` and `rating_info_change`.

### Service Layer Issues (CRITICAL)

1. **Broken Transaction Atomicity:**
   ```python
   # Current flow in process_new_match():
   await db.commit()  # Line 85 - commits match data
   await glicko2_engine.update_ratings_for_match(db, new_match)  # Can fail!
   # If rating engine fails, match exists but ratings are wrong
   ```

   This means a match can be recorded without ratings being updated, leaving the system in an inconsistent state.

2. **No Participant Validation:**
   - No check for minimum 2 participants
   - No check for duplicate players
   - No validation of team structures
   - Empty participant lists accepted

3. **Hardcoded Default Ratings:**
   ```python
   DEFAULT_RATING_INFO = {"rating": 1500.0, "rd": 350.0, "vol": 0.06}
   # Should be configurable per-game
   ```

4. **Silent Failures in Rating Engine:**
   ```python
   # glicko2_engine.py
   if not profile:
       continue  # Silently skips missing profiles!
   ```

### API Layer Issues

1. **No Pagination:**
   ```python
   # Current - returns ALL records
   @router.get("/", response_model=list[match_schema.MatchRead])
   async def read_matches(...):
       query = select(Match).order_by(Match.id)  # No limit!
   ```

2. **Unhandled Database Exceptions:**
   ```python
   # Creating duplicate player throws IntegrityError, not HTTPException
   new_player = Player(**player_in.model_dump())
   await db.commit()  # Throws raw SQLAlchemy error
   ```

3. **Missing Core Endpoints:**
   - `GET /games/{game_id}/leaderboard`
   - `GET /players/{player_id}/stats`
   - `GET /players/{player_id}/matches`
   - `GET /health`
   - `PUT /matches/{match_id}` (update with cascade)

4. **No Idempotency Support** - Multiple identical POST requests create duplicates.

5. **No Request Logging** - Cannot audit API usage or debug production issues.

### Test Coverage Gaps

1. **No Error Scenario Tests:**
   - Duplicate player creation
   - Invalid game_id references
   - Missing game profiles

2. **No Transaction Rollback Tests:**
   - Partial failure scenarios
   - Database connection failures

3. **No Concurrency Tests:**
   - Simultaneous match creation
   - Race conditions on rating updates

4. **No Validation Tests:**
   - Invalid outcome formats
   - Invalid team structures
   - Empty participant lists

---

## Match Update Cascade: The Rating Recalculation Problem

Updating historical match data is one of the most architecturally challenging features in a rating system. When a match is corrected (wrong score, wrong players, wrong outcome), all subsequent ratings become invalid and must be recalculated.

### The Problem

Consider this scenario:
```
Match 1: Alice vs Bob → Alice wins → Alice: 1520, Bob: 1480
Match 2: Bob vs Carol → Bob wins → Bob: 1510, Carol: 1470
Match 3: Alice vs Carol → Carol wins → Alice: 1490, Carol: 1510

User discovers Match 1 was recorded wrong - Bob actually won.

Now what? All ratings are wrong:
- Match 1 recalc: Alice: 1480, Bob: 1520 (reversed)
- Match 2 recalc: Bob: 1550, Carol: 1470 (Bob started higher)
- Match 3 recalc: Alice: 1450, Carol: 1510 (Alice started lower)
```

Every match after the corrected one must be recalculated in chronological order, using the corrected ratings as inputs.

### Architectural Approaches

#### Approach 1: Full Forward Recalculation (Recommended for MVP)

**How it works:**
1. Identify the updated match's `played_at` timestamp
2. Query all matches for the same game with `played_at >= updated_match.played_at`
3. Reset all affected players' ratings to their state *before* the updated match
4. Replay all matches in chronological order, recalculating ratings

**Implementation:**
```python
async def recalculate_ratings_from_match(
    db: AsyncSession,
    match_id: int
) -> RecalculationResult:
    """
    Recalculate all ratings affected by updating a historical match.
    """
    match = await db.get(Match, match_id)
    game_id = match.game_id

    # 1. Get all matches from this point forward
    affected_matches = await db.execute(
        select(Match)
        .where(Match.game_id == game_id)
        .where(Match.played_at >= match.played_at)
        .order_by(Match.played_at)
    )

    # 2. Get all affected players
    affected_player_ids = set()
    for m in affected_matches:
        for p in m.participants:
            affected_player_ids.add(p.player_id)

    # 3. Reset ratings to "before" state of first affected match
    for player_id in affected_player_ids:
        profile = await get_game_profile(db, player_id, game_id)
        first_participation = get_first_participation(player_id, affected_matches)
        if first_participation.rating_info_before:
            profile.rating_info = first_participation.rating_info_before

    # 4. Replay all matches in order
    for m in affected_matches:
        await rating_engine.update_ratings_for_match(db, m)

    await db.commit()
    return RecalculationResult(matches_affected=len(affected_matches))
```

**Pros:**
- Simple to implement and understand
- Guarantees correctness
- No additional data structures needed

**Cons:**
- O(n) where n = matches after the update
- Slow for old matches in active games
- All-or-nothing operation

**Performance Characteristics:**
- 100 matches: < 1 second
- 1,000 matches: 5-10 seconds
- 10,000 matches: 1-2 minutes

**Mitigation:** For MVP with friends (likely < 500 total matches), this is perfectly acceptable.

#### Approach 2: Event Sourcing with Snapshots

**How it works:**
- Store all match events as immutable records
- Periodically create rating "snapshots" at checkpoints
- On update, find nearest snapshot before the change and replay forward

**Implementation Sketch:**
```python
class RatingSnapshot(Base):
    __tablename__ = "rating_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    snapshot_at: Mapped[datetime]
    ratings: Mapped[dict]  # {player_id: rating_info}
    match_id: Mapped[int]  # Last match included in snapshot
```

**Pros:**
- Can limit recalculation to snapshot intervals
- Enables "what-if" analysis without mutation
- Full audit trail

**Cons:**
- Significantly more complex
- Additional storage requirements
- Snapshot management overhead

**Recommendation:** Defer to post-MVP.

#### Approach 3: Incremental Delta Recalculation

**How it works:**
- Track rating deltas per match, not absolute ratings
- On update, calculate new deltas and propagate changes

**Why it doesn't work for Glicko-2:**
- Glicko-2 is non-linear (RD and volatility interact)
- Can't simply add/subtract deltas
- Each calculation depends on opponent ratings at that moment

**Recommendation:** Not viable for this rating system.

### Implementation Plan for Match Updates

**Phase 0 Tasks (Foundation):**

| Task | Hours | Description |
|------|-------|-------------|
| Add `updated_at` timestamps to all models | 2 | Track when records change |
| Create `MatchUpdate` schema with validation | 3 | Define what can/cannot be updated |
| Implement optimistic locking | 2 | Prevent concurrent update conflicts |
| Add match versioning/audit table | 4 | Track change history |

**Phase 1 Tasks (Core Implementation):**

| Task | Hours | Description |
|------|-------|-------------|
| Implement rating snapshot storage | 4 | Store rating state before each match |
| Build forward recalculation service | 8 | Core algorithm implementation |
| Create `PUT /matches/{id}` endpoint | 4 | API with validation and cascade trigger |
| Add recalculation progress tracking | 3 | For long-running operations |
| Build rollback capability | 4 | Undo failed recalculations |
| Comprehensive test suite | 6 | Edge cases, concurrent updates |

**Total: ~40 hours**

### Validation Rules for Match Updates

To prevent invalid updates that would corrupt the rating system:

1. **Immutable After Threshold:**
   ```python
   MAX_UPDATE_AGE_DAYS = 30  # Configurable
   if (datetime.now() - match.played_at).days > MAX_UPDATE_AGE_DAYS:
       raise MatchTooOldToUpdateError()
   ```

2. **Cannot Change Game:**
   ```python
   if update.game_id and update.game_id != match.game_id:
       raise CannotChangeMatchGameError()
   ```

3. **Player Changes Require Full Recalculation:**
   ```python
   if set(update.player_ids) != set(original.player_ids):
       # Must recalculate from this match forward
       requires_cascade = True
   ```

4. **Concurrent Update Protection:**
   ```python
   if match.version != update.expected_version:
       raise ConcurrentModificationError()
   ```

5. **Outcome Validation:**
   ```python
   if not is_valid_outcome(update.outcome, match.game):
       raise InvalidOutcomeError()
   ```

### User Experience Considerations

1. **Warning Before Cascade:**
   ```
   "Updating this match will recalculate ratings for 47 subsequent matches.
    This may take up to 30 seconds. Continue?"
   ```

2. **Progress Indication:**
   - Show recalculation progress for large cascades
   - Allow background processing with notification on completion

3. **Preview Changes:**
   - Show rating diffs before confirming update
   - "Alice: 1520 → 1485 (-35), Bob: 1480 → 1515 (+35)"

4. **Audit Log:**
   - Record who changed what, when
   - Enable undo within a time window

---

## Project Architecture

### Technology Stack

**Backend:**
| Component | Technology | Purpose |
|-----------|------------|---------|
| Framework | FastAPI | Async REST API |
| ORM | SQLAlchemy 2.0 | Database abstraction |
| Migrations | Alembic | Schema version control |
| Validation | Pydantic | Request/response schemas |
| Server | Uvicorn | ASGI application server |
| Dev Database | SQLite + aiosqlite | Development persistence |
| Prod Database | PostgreSQL | Production persistence (planned) |

**Frontend (Proposed):**
| Component | Technology | Rationale |
|-----------|------------|-----------|
| Framework | React | Industry standard, excellent ecosystem |
| Language | TypeScript | Type safety, better DX |
| Build Tool | Vite | Fast development, modern bundling |
| Styling | Tailwind CSS | Rapid prototyping, utility-first |
| State | React Query + Zustand | Server state + client state |
| Charts | Recharts | React-native charting library |
| HTTP | Axios | Clean API client |

**Infrastructure (Proposed):**
| Component | Technology | Rationale |
|-----------|------------|-----------|
| Containerization | Docker | Consistent deployments |
| Hosting | Railway / Render | Simple PaaS with free tiers |
| CI/CD | GitHub Actions | Integrated with repository |
| Monitoring | Sentry (free tier) | Error tracking |

### System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                            │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────────┐ │
│  │   Match   │  │ Leaderbd  │  │  Player   │  │   Matchmaking     │ │
│  │  Entry    │  │   View    │  │  Stats    │  │    Interface      │ │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────────┬─────────┘ │
└────────┼──────────────┼──────────────┼──────────────────┼───────────┘
         │              │              │                  │
         └──────────────┼──────────────┼──────────────────┘
                        │              │
                   HTTP/REST API
                        │              │
┌───────────────────────┴──────────────┴──────────────────────────────┐
│                        BACKEND (FastAPI)                            │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      API Layer (/api/)                        │  │
│  │   /players  │  /games  │  /matches  │  /leaderboard*  │ ...  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                   Service Layer (/services/)                  │  │
│  │   match_service  │  matchmaking_service*  │  analytics*       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Rating Layer (/rating/)                    │  │
│  │     glicko2_engine  │  dummy_engine  │  (future: ML models)   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                   Data Layer (/db/)                           │  │
│  │   Player  │  Game  │  GameProfile  │  Match  │  Participant   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                          ┌──────┴──────┐
                          │  Database   │
                          │ PostgreSQL  │
                          └─────────────┘

* = Not yet implemented
```

### Data Flow for Key Operations

**Recording a Match (Target Flow After Phase 0A):**
```
User → Frontend Form → POST /matches/ → match_service.process_new_match()
  → Begin transaction
  → Create Match + MatchParticipant records
  → get_or_create_game_profile() for each player
  → Store rating_info_before
  → Dispatch to rating engine (glicko2_engine.update_ratings_for_match)
  → Calculate new ratings per Glicko-2 algorithm
  → Update GameProfile.rating_info
  → Store rating_info_change
  → Commit entire transaction (match + ratings atomically)
  → Return complete Match object → Frontend displays result
```
*Note: Current implementation incorrectly commits before rating calculation. See Phase 0A for fix.*

**Matchmaking (Planned):**
```
User → Select players + constraints → POST /matchmaking/generate
  → Fetch all players' GameProfiles for selected game
  → Create skill distributions per player (Gaussian from rating + RD)
  → Generate possible team configurations
  → Evaluate each configuration:
    → Superposition team distributions
    → Calculate fairness score (overlap of team distributions)
  → Simulated annealing optimization
    → Start with random configuration
    → Perturb and accept/reject based on temperature schedule
  → Return top N configurations → Frontend displays options
```

---

## Development Roadmap

### Phase 0: Foundation Refactoring & Production-Quality Standards
**Goal:** Aggressively refactor existing code to production-quality standards before adding new features. This phase is critical—building on a weak foundation will compound technical debt.

**Production-Quality Standards We're Targeting:**
- All database operations are atomic and properly handle failures
- All API inputs are validated with meaningful error messages
- All JSON fields have typed schemas
- Connection management is production-ready
- Test coverage > 85% with error scenario coverage
- No silent failures anywhere in the codebase

---

#### Phase 0A: Critical Infrastructure Fixes ✅ COMPLETED

**Completed:** 2025-12-20

| Task | Hours | Status | File(s) Modified |
|------|-------|--------|------------------|
| Externalize DATABASE_URL to environment variable | 1 | ✅ Done | `src/rankforge/db/session.py`, `.env.example` |
| Add connection pool configuration | 2 | ✅ Done | `src/rankforge/db/session.py` |
| Fix transaction atomicity in match_service | 4 | ✅ Done | `src/rankforge/services/match_service.py`, rating engines |
| Add try-except with rollback to get_db() | 1 | ✅ Done | `src/rankforge/db/session.py` |
| Add FastAPI lifespan for connection cleanup | 2 | ✅ Done | `src/rankforge/main.py` |

**Subtotal:** 10 hours

**Completion Criteria:**
- [x] Application starts with DATABASE_URL environment variable
- [x] Connection pool configured with pool_size, max_overflow, pool_pre_ping
- [x] Match creation is fully atomic (match + ratings in single transaction)
- [x] Database errors result in proper rollback
- [x] Health check endpoint added (`GET /health`)

---

#### Phase 0B: Data Layer Refactoring

The data layer has the most issues and requires significant restructuring.

**Database Models Refactoring:** ✅ COMPLETED (2025-12-20)

| Task | Hours | Status | File(s) Modified |
|------|-------|--------|------------------|
| Add database indexes to foreign key columns | 2 | ✅ Done | `src/rankforge/db/models.py` |
| Add `created_at`, `updated_at` to GameProfile, Match, MatchParticipant | 3 | ✅ Done | `src/rankforge/db/models.py` (via mixins) |
| Add `version` column for optimistic locking | 2 | ✅ Done | `src/rankforge/db/models.py` (VersionMixin) |
| Standardize rating_info keys (rating, rd, vol) | 3 | ✅ Done | `src/rankforge/db/models.py` (RatingInfo TypedDict) |
| Add `deleted_at` for soft delete support | 2 | ✅ Done | `src/rankforge/db/models.py` (SoftDeleteMixin) |
| Fix cascade behavior on Player.match_participations | 1 | ✅ Done | `src/rankforge/db/models.py` (passive_deletes=True) |
| Create Alembic migration for all schema changes | 3 | ✅ Done | `src/alembic/versions/20251220_add_timestamps_indexes_versioning.py` |

**Subtotal:** 16 hours

**Implementation Notes:**
- Created `TimestampMixin`, `VersionMixin`, and `SoftDeleteMixin` for code reuse
- Created `RatingInfo` TypedDict documenting standard keys: `rating`, `rd`, `vol`
- All FK columns now have `index=True`
- Migration handles SQLite constraints (constant defaults for ALTER TABLE)
- All 24 tests passing, mypy clean, ruff clean

**Pydantic Schema Refactoring:** ✅ COMPLETED (2025-12-20)

| Task | Hours | Status | File(s) Modified |
|------|-------|--------|------------------|
| Create RatingStrategy enum, validate in GameCreate | 2 | ✅ Done | `src/rankforge/schemas/game.py` |
| Create RatingInfo Pydantic model | 3 | ✅ Done | `src/rankforge/schemas/common.py` (NEW) |
| Create outcome schema variants (Binary, Ranked) | 4 | ✅ Done | `src/rankforge/schemas/match.py` |
| Add field validation (min/max length) | 2 | ✅ Done | `src/rankforge/schemas/player.py`, `game.py` |
| Add rating_info_before/change to MatchParticipantRead | 1 | ✅ Done | `src/rankforge/schemas/match.py` |
| Create GameProfile schemas for leaderboard | 2 | ✅ Done | `src/rankforge/schemas/game_profile.py` (NEW) |
| Create MatchUpdate schema with validation rules | - | Deferred | Will implement in Phase 1 with match updates |

**Subtotal:** 14 hours

**Implementation Notes:**
- Created `RatingStrategy` enum with `GLICKO2` and `DUMMY` values
- Created `RatingInfo` Pydantic model with proper validation (rating 0-4000, rd 0-500, vol 0-1.0)
- Created flexible `BinaryOutcome` and `RankedOutcome` with `ConfigDict(extra="allow")` to support game-specific rating factors
- Used discriminated union `Outcome = Annotated[Union[BinaryOutcome, RankedOutcome], Field()]`
- Added field validation to Player (name: 2-100 chars) and Game (name: 2-200 chars)
- Created `GameProfileRead` and `GameProfileWithPlayer` schemas for leaderboard support
- All 24 tests passing, mypy clean, ruff clean

**Service Layer Refactoring:** ✅ COMPLETED (2025-12-20)

| Task | Hours | Status | Issue Addressed |
|------|-------|--------|-----------------|
| Create custom exception hierarchy | 3 | ✅ Done | Generic ValueError usage |
| Add anonymous player support (is_anonymous flag + migration) | 2 | ✅ Done | Support casual matches with unknown players |
| Update match schema to allow optional player_id | 1 | ✅ Done | Enable auto-creation of anonymous players |
| Add participant validation (min 2, no duplicates, 2+ teams) | 3 | ✅ Done | Invalid matches accepted |
| Replace silent failures with explicit errors in glicko2_engine | 2 | ✅ Done | Silent skips |
| Update dummy_engine for consistency with exception handling | 1 | ✅ Done | Consistency across rating engines |
| Add API exception handlers in match.py | 2 | ✅ Done | Map exceptions to HTTP status codes |
| Add structured logging throughout | 3 | ✅ Done | No request logging |
| Move default rating to Game model (configurable per-game) | - | Deferred | Will implement in Phase 1 |

**Subtotal:** 17 hours

**Implementation Notes:**
- Created `src/rankforge/exceptions.py` with custom exception hierarchy:
  - `RankForgeError` (base) → `ResourceNotFoundError` (404) → `GameNotFoundError`, `PlayerNotFoundError`, `GameProfileNotFoundError`
  - `RankForgeError` → `ValidationError` (422) → `InsufficientParticipantsError`, `DuplicatePlayerError`, `InsufficientTeamsError`
  - `RankForgeError` → `RatingEngineError` (500) → `NonCompetitiveMatchError`, `RatingCalculationError`
- Added `is_anonymous` boolean field to Player model with index for leaderboard filtering
- Created migration `20251220_add_is_anonymous_to_players.py`
- Match schema now accepts `player_id: int | None` - when None, uses shared "Unknown" player
- Unknown player support: A single shared player named "Unknown" (with `is_anonymous=True`) is used for all unknown participants, avoiding database bloat. The Unknown player is exempt from duplicate validation, allowing multiple unknowns in one match.
- Validation: minimum 2 participants, no duplicate players (except Unknown), at least 2 teams
- All rating engines now raise exceptions instead of silent failures
- API returns proper HTTP status codes: 404 (not found), 422 (validation), 500 (rating engine)
- All 24 tests passing, mypy clean, ruff clean

---

#### Phase 0C: API Layer Improvements ✅ COMPLETED

**Completed:** 2025-12-31

| Task | Hours | Priority | Status | Issue Addressed |
|------|-------|----------|--------|-----------------|
| Add pagination to all list endpoints | 4 | CRITICAL | ✅ Done | Returns all records |
| Add filtering (by game_id, player_id, date range) | 3 | HIGH | ✅ Done | No filtering |
| Add sorting options | 2 | MEDIUM | ✅ Done | Hardcoded order |
| Catch IntegrityError, return proper HTTPException | 2 | HIGH | ✅ Done | Raw DB errors |
| Add GET /games/{game_id}/leaderboard endpoint | 4 | HIGH | ✅ Done | Missing core feature |
| Add GET /players/{player_id}/stats endpoint | 4 | HIGH | ✅ Done | Missing core feature |
| Add GET /players/{player_id}/matches endpoint | 3 | MEDIUM | ✅ Done | Missing feature |
| Add GET /health endpoint | 1 | MEDIUM | ✅ Done | No health check |
| Add global exception handler | 2 | MEDIUM | ✅ Done | Inconsistent errors |
| Add request/response logging middleware | 2 | MEDIUM | ✅ Done | No audit trail |

**Subtotal:** 27 hours

**Implementation Notes:**
- Created `src/rankforge/schemas/pagination.py` with `PaginatedResponse` generic, sort field enums, and `SortOrder` enum
- Created `src/rankforge/schemas/leaderboard.py` with `LeaderboardEntry` schema
- Created `src/rankforge/schemas/player_stats.py` with `GameStats` and `PlayerStats` schemas
- Created `src/rankforge/middleware/logging.py` with `RequestLoggingMiddleware` that adds X-Request-ID header
- Added global exception handlers in `main.py` for `ResourceNotFoundError` (404), `ValidationError` (422), `RatingEngineError` (500), `IntegrityError` (409/400), `SQLAlchemyError` (500), and generic `Exception` (500)
- Updated all list endpoints with pagination (skip/limit), sorting (sort_by/sort_order), and soft delete filtering
- Added filtering to matches endpoint: game_id, player_id, played_after, played_before
- Added `include_anonymous` filter to players list endpoint
- New endpoints: `GET /games/{game_id}/leaderboard`, `GET /players/{player_id}/stats`, `GET /players/{player_id}/matches`
- All 25 tests passing, mypy clean, ruff clean

---

#### Phase 0D: Test Coverage Expansion ✅ COMPLETED

**Completed:** 2025-01-04

| Task | Hours | Status | Issue Addressed |
|------|-------|--------|-----------------|
| Add error scenario tests (duplicates, not found, invalid) | 4 | Done | No error tests |
| Add transaction rollback tests | 3 | Done | Untested atomicity |
| Add validation tests (invalid outcomes, teams, empty) | 3 | Done | No validation tests |
| Add Glicko-2 edge case tests (extreme RD, rating diffs) | 3 | Done | Math edge cases |
| Add API pagination/filtering tests | 2 | Done | New features |
| Add concurrent operation tests | 4 | Done | Race conditions |
| Fill remaining test gaps (extreme ratings, team draws, metadata) | 3 | Done | Current gaps |

**Subtotal:** 22 hours

**Implementation Notes:**

- Test suite expanded from 143 to 162 tests (~3,800+ lines of test code)
- Added 8 extreme rating edge case tests (ratings 0-3500, RD 10-400, volatility 0.001-0.15)
- Added 4 larger team draw tests (3v3, 4v4, 3-team draws)
- Added 3 leaderboard tiebreaker tests (stable ordering, correct sort, active players only)
- Added 4 match metadata edge case tests (empty, omitted, complex structures, unicode)
- All 162 tests passing, mypy clean, ruff clean

---

#### Phase 0E: Development Environment & Cleanup

| Task | Hours | Priority | Issue Addressed |
|------|-------|----------|-----------------|
| Set up Docker development environment | 4 | HIGH | Inconsistent setup |
| Create docker-compose with PostgreSQL | 2 | HIGH | SQLite limitations |
| Consolidate 24 import scripts into single importer | 4 | LOW | Script sprawl |
| Update README with new setup instructions | 2 | MEDIUM | Outdated docs |
| Create .env.example with all variables | 1 | HIGH | Missing template |

**Subtotal:** 13 hours

---

#### Phase 0 Summary

| Sub-Phase | Hours | Focus | Status |
|-----------|-------|-------|--------|
| 0A: Critical Infrastructure | 10 | Must fix first | ✅ Complete |
| 0B: Data Layer | 50 | Models, schemas, services | ✅ Complete |
| 0C: API Layer | 27 | Endpoints, error handling | ✅ Complete |
| 0D: Test Coverage | 22 | Comprehensive testing | ✅ Complete |
| 0E: Dev Environment | 13 | Docker, cleanup | Pending |
| **Total** | **122** | **20-40 weeks at 3-6 hrs/week** | **4/5 Done** |

**Current Status (2025-01-04):** Phases 0A-0D complete. Only Phase 0E (Docker setup) remains before starting Phase 1 (Matchmaking Algorithm).

**Completion Criteria:**

- [x] All critical infrastructure issues resolved (Phase 0A)
- [x] Database schema includes indexes, timestamps, versioning (Phase 0B)
- [x] All JSON fields have typed schemas with validation (Phase 0B)
- [x] Transaction atomicity verified with tests (Phase 0D)
- [x] API returns proper errors for all failure cases (Phase 0C)
- [x] Pagination works on all list endpoints (Phase 0C)
- [x] Test coverage comprehensive (162 tests) (Phase 0D)
- [ ] Docker development environment functional (Phase 0E - pending)
- [x] Zero silent failures in codebase (Phase 0B)
- [x] All TODO comments replaced with implementations (Phase 0B)

**Code That Should Be Rewritten (Not Just Refactored):**

1. **match_service.process_new_match()** - Transaction handling is fundamentally broken. Needs complete rewrite with proper atomic boundaries.

2. **get_db() in session.py** - Needs rewrite with error handling, proper lifecycle management, and configuration.

3. **All Pydantic schemas** - Current approach of `pass` in child classes provides no value. Need complete redesign with proper validation.

4. **Error handling throughout** - No consistent pattern exists. Need custom exception hierarchy and global handler.

---

### Phase 1: Matchmaking Algorithm Implementation
**Goal:** Implement the novel matchmaking algorithm that makes this project unique

**Tasks:**

| Task | Hours | Priority |
|------|-------|----------|
| Design matchmaking service interface and schemas | 3-4 | High |
| Implement skill distribution modeling (Gaussian from rating + RD) | 4-5 | High |
| Implement team distribution superposition | 4-5 | High |
| Implement fairness scoring function (distribution overlap) | 3-4 | High |
| Implement configuration space enumeration for small N | 3-4 | Medium |
| Implement simulated annealing optimizer | 6-8 | High |
| Add matchmaking endpoint: `POST /matchmaking/generate` | 3-4 | High |
| Add constraints handling (player preferences, must-play-together, etc.) | 4-5 | Medium |
| Write comprehensive tests for matchmaking | 5-6 | High |
| Document algorithm with mathematical notation | 3-4 | Medium |

**Estimated Total:** 39-49 hours (8-16 weeks at 3-6 hrs/week)

**Completion Criteria:**
- [ ] Matchmaking generates balanced teams for 4-12 players
- [ ] Fairness score accurately reflects team balance
- [ ] Algorithm handles constraints (exclude players, force teammates)
- [ ] Performance: <2 seconds for 12 players
- [ ] Algorithm documented with examples

---

### Phase 2: Frontend Development
**Goal:** Build user-facing interface for core features

**Tasks:**

| Task | Hours | Priority |
|------|-------|----------|
| Set up React + TypeScript + Vite project structure | 2-3 | High |
| Configure Tailwind CSS and design system | 2-3 | High |
| Create API client with Axios and types from OpenAPI | 3-4 | High |
| Build navigation and layout components | 3-4 | High |
| Build Match Entry form (select game, players, outcomes) | 6-8 | High |
| Build Leaderboard view (sortable table with ratings/stats) | 5-6 | High |
| Build Player Profile page (stats, match history, rating graph) | 6-8 | High |
| Build Matchmaking interface (player selection, generate teams) | 8-10 | High |
| Build Game Selection/Management page | 3-4 | Medium |
| Implement responsive design for mobile | 4-5 | Medium |
| Add loading states, error handling, toast notifications | 3-4 | Medium |
| Build rating history chart (line chart over time) | 4-5 | Medium |

**Estimated Total:** 50-64 hours (10-21 weeks at 3-6 hrs/week)

**Completion Criteria:**
- [ ] All four core user flows functional (record match, view leaderboard, create teams, view stats)
- [ ] Responsive design works on mobile devices
- [ ] Loading and error states properly handled
- [ ] No console errors in production build

---

### Phase 3: Integration, Polish & Deployment
**Goal:** Connect all pieces, deploy to production, and prepare for public use

**Tasks:**

| Task | Hours | Priority |
|------|-------|----------|
| Create production Docker configuration (multi-stage build) | 3-4 | High |
| Set up PostgreSQL for production | 2-3 | High |
| Configure CORS and security headers | 2 | High |
| Deploy backend to Railway/Render | 3-4 | High |
| Deploy frontend to Vercel/Netlify | 2-3 | High |
| Set up CI/CD with GitHub Actions (test + deploy) | 4-5 | High |
| Configure environment variables for production | 2 | High |
| Add error tracking with Sentry | 2 | Medium |
| Performance testing and optimization | 4-5 | Medium |
| Mobile PWA configuration (installable) | 3-4 | Low |
| Add basic analytics (match counts, active users) | 2-3 | Low |

**Estimated Total:** 30-38 hours (6-13 weeks at 3-6 hrs/week)

**Completion Criteria:**
- [ ] Application deployed and accessible via public URL
- [ ] CI/CD pipeline runs tests and deploys on merge to main
- [ ] Zero downtime deployments configured
- [ ] Error tracking operational
- [ ] Performance benchmarks met (<200ms API response times)

---

### Phase 4: Documentation & Open Source Preparation
**Goal:** Make project accessible and professional for public release

**Tasks:**

| Task | Hours | Priority |
|------|-------|----------|
| Write comprehensive README with screenshots | 3-4 | High |
| Create installation and setup guide | 2-3 | High |
| Document API with examples and use cases | 3-4 | High |
| Write architecture documentation with diagrams | 3-4 | High |
| Create CONTRIBUTING.md with guidelines | 2 | Medium |
| Add CODE_OF_CONDUCT.md | 0.5 | Medium |
| Create issue and PR templates | 1 | Medium |
| Write algorithm documentation (the "paper") | 5-6 | High |
| Create demo video or GIF walkthrough | 2-3 | Medium |
| Write blog post / case study for portfolio | 4-5 | Medium |
| Optimize GitHub repository presentation | 2 | Medium |

**Estimated Total:** 28-35 hours (5-12 weeks at 3-6 hrs/week)

**Completion Criteria:**
- [ ] New contributor can set up project in <15 minutes
- [ ] API fully documented with examples
- [ ] Algorithm explained clearly for technical and non-technical audiences
- [ ] Repository has professional presentation (README, badges, etc.)

---

## MVP Definition

### Core Features (Must Have)

1. **Match Recording**
   - Select game from dropdown
   - Select players from list or add new
   - Assign players to teams
   - Record outcome (win/loss or ranks)
   - Automatic rating calculation on submit
   - Display rating changes after submission

2. **Leaderboard Display**
   - View all players ranked by rating for a game
   - Show rating, rating deviation, matches played
   - Sortable columns
   - Filter by game

3. **Matchmaking Generation**
   - Select active players for a session
   - Generate balanced team configurations
   - Display fairness score for each option
   - Accept configuration or regenerate

4. **Player Statistics**
   - View individual player profile
   - Show win/loss record per game
   - Display rating history graph
   - List recent matches

### User Flows

**1. Recording a Match:**
```
1. User opens app → Dashboard
2. Click "Record Match" button
3. Select game (e.g., "Pickleball")
4. If new players: click "Add Player" → enter name → save
5. Drag/drop or select players into Team 1 and Team 2
6. Select winner (Team 1 / Team 2 / Draw)
7. Optionally add score and notes
8. Click "Submit Match"
9. View rating changes for all participants
10. Confirm or record another match
```

**2. Viewing Leaderboard:**
```
1. User opens app → Dashboard
2. Click "Leaderboards" in navigation
3. Select game from dropdown
4. View sorted list of players by rating
5. Click column headers to sort by other metrics
6. Click player name to view profile
```

**3. Creating Balanced Teams:**
```
1. User opens app → Dashboard
2. Click "Matchmaking" in navigation
3. Select game
4. Check boxes next to available players (e.g., 8 players)
5. Set constraints (optional): "Keep X and Y together"
6. Click "Generate Teams"
7. View 3-5 suggested configurations with fairness scores
8. Click "Use This" to copy or start match
```

**4. Analyzing Player Stats:**
```
1. Click player name from leaderboard or search
2. View profile page with:
   - Rating summary across games
   - Win/loss pie chart
   - Rating over time line chart
   - Recent match list with ratings before/after
3. Click on match to see full match details
```

### Technical Requirements

**Performance:**
- API response time < 200ms for all endpoints
- Matchmaking for 12 players < 2 seconds
- Frontend initial load < 3 seconds
- Smooth animations at 60fps

**Security:**
- Input validation on all endpoints
- SQL injection prevention (ORM handles this)
- XSS prevention in frontend
- CORS configured for production domains only

**Scalability:**
- Support 1,000+ matches in database
- Support 100+ players across games
- Async architecture ready for concurrent requests

**Code Quality:**
- All code passes Ruff linting
- All code passes Mypy type checking
- Test coverage > 80%
- No critical security vulnerabilities

---

## Post-MVP Feature Roadmap

### Near-term Enhancements (Next 3-6 months post-MVP)

**Tier 1: High-Priority Extensions**

1. **Match Editing/Correction**
   - Value: Fix data entry mistakes without deleting matches
   - Complexity: Medium (need to recalculate affected ratings)
   - Estimated effort: 8-10 hours

2. **Rating History API**
   - Value: Power frontend graphs, enable analytics
   - Complexity: Low (query existing data differently)
   - Estimated effort: 4-6 hours

3. **Bulk Match Import UI**
   - Value: Onboard historical data easily
   - Complexity: Medium (CSV parsing, validation UI)
   - Estimated effort: 10-12 hours

4. **Game Configuration UI**
   - Value: Non-technical users can add games
   - Complexity: Low (CRUD form)
   - Estimated effort: 4-5 hours

**Tier 2: Medium-Priority Additions**

5. **Player Aliases/Nicknames**
   - Value: Handle players known by multiple names
   - Complexity: Low
   - Estimated effort: 3-4 hours

6. **Match Comments/Notes**
   - Value: Add context to matches
   - Complexity: Low
   - Estimated effort: 2-3 hours

7. **Rating Predictions**
   - Value: "What if" scenarios before matches
   - Complexity: Medium
   - Estimated effort: 6-8 hours

8. **Export to CSV/JSON**
   - Value: Data portability, analysis in other tools
   - Complexity: Low
   - Estimated effort: 3-4 hours

9. **Claim Unknown Player History**
   - Value: Convert a recurring unknown player's match history to a named player
   - Use case: Someone who was initially "Unknown" becomes a regular, want to merge their history
   - Implementation: Create endpoint to reassign all MatchParticipant records from Unknown player to a target player, then recalculate ratings from the earliest affected match forward
   - Complexity: Medium (requires rating recalculation cascade)
   - Estimated effort: 6-8 hours (depends on match update cascade from Phase 1)

### Long-term Vision (6+ months)

**Experimental Features:**

1. **ML-Enhanced Rating System**
   - Replace traditional "expectation of win" calculations with ML models
   - Experiment with architectures:
     - Random Forest on feature-engineered match data
     - MLPs on player rating vectors
     - Attention mechanisms for player interaction modeling
     - LLMs for contextual understanding (ambitious)
   - Compare ML predictions vs. Glicko-2 expected outcomes
   - Measure: Does ML improve fairness prediction accuracy?
   - Estimated effort: 40-60 hours for initial prototype

2. **Advanced Matchmaking**
   - Refine distribution superposition with learned parameters
   - Add user-configurable optimization objectives
   - Explore multi-objective optimization (fairness + fun factor)
   - Consider fatigue/variety constraints
   - Estimated effort: 20-30 hours

3. **Social Features**
   - Friend lists and groups
   - Match challenges between players
   - Achievement badges
   - Estimated effort: 30-40 hours

4. **Tournament Mode**
   - Bracket generation (single/double elimination, round robin)
   - Tournament ratings separate from ladder ratings
   - Seeding based on current ratings
   - Estimated effort: 40-50 hours

**Platform Expansion:**

5. **Mobile Native App** (React Native)
   - Value: Better mobile UX, offline support
   - Complexity: High
   - Estimated effort: 80-100 hours

6. **Discord Bot Integration**
   - Record matches via slash commands
   - View leaderboards in Discord
   - Matchmaking via reactions
   - Estimated effort: 20-25 hours

7. **Multi-tenant Support**
   - Separate instances for different friend groups/organizations
   - Admin roles and permissions
   - Estimated effort: 30-40 hours

---

## Technical Implementation Details

### Rating System Architecture

**Current Implementation: Glicko-2**

Located in [glicko2_engine.py](src/rankforge/rating/glicko2_engine.py), the implementation follows Mark Glickman's paper exactly:

```python
@dataclass
class Glicko2Rating:
    mu: float = 1500.0      # Rating (skill estimate)
    phi: float = 350.0      # Rating Deviation (uncertainty)
    sigma: float = 0.06     # Volatility (consistency)
```

**Key Algorithm Steps:**
1. Convert to Glicko-2 scale (divide by 173.7178)
2. Compute estimated variance `v`
3. Compute estimated improvement `delta`
4. Determine new volatility `sigma'` via bisection method
5. Update rating deviation to pre-rating period value
6. Update rating and rating deviation
7. Convert back to Glicko scale

**Score Calculation:**
- Binary outcomes: win=1.0, loss=0.0, draw=0.5
- Ranked outcomes: normalized by (numOpponents - (rank-1)) / numOpponents
- Each player rated against all opponents on opposing teams

**Extension Points:**
- New rating engines implement `update_ratings_for_match(db, match)` function
- Game's `rating_strategy` field routes to appropriate engine
- Engines can be hot-swapped without schema changes

### Matchmaking Algorithm (Planned)

**Core Concept: Skill Distribution Superposition**

Each player's skill is modeled as a Gaussian distribution:
```
Player_i ~ N(μ_i, σ_i)
where μ = rating, σ = rating_deviation
```

A team's skill is the sum of player skills (superposition):
```
Team ~ N(Σμ_i, √(Σσ_i²))
```

**Fairness Scoring:**

The fairness of a matchup is the probability that teams are evenly matched, calculated as the overlap of team distributions:
```
Fairness = P(|Team1 - Team2| < threshold)
         = area under min(pdf_Team1_wins, pdf_Team2_wins)
```

Higher overlap = more uncertain outcome = more balanced match.

**Simulated Annealing Optimization:**

For N players forming M teams:
1. Initialize random valid configuration
2. Set temperature T = T_max
3. While T > T_min:
   - Perturb: swap two random players between teams
   - Calculate ΔFairness
   - If improved: accept
   - If worse: accept with probability exp(ΔFairness/T)
   - Cool: T = T * cooling_rate
4. Return best configuration found

**Configuration:**
```python
DEFAULT_MATCHMAKING_CONFIG = {
    "T_max": 1.0,
    "T_min": 0.001,
    "cooling_rate": 0.99,
    "iterations_per_temp": 10,
    "num_results": 5,  # Return top N configurations
}
```

### Data Models

**Entity Relationship Diagram:**
```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Player    │     │    Game     │     │   GameProfile   │
├─────────────┤     ├─────────────┤     ├─────────────────┤
│ id (PK)     │───┐ │ id (PK)     │───┐ │ id (PK)         │
│ name        │   │ │ name        │   │ │ player_id (FK)  │←─┐
│ created_at  │   │ │ rating_strat│   └→│ game_id (FK)    │  │
└─────────────┘   │ │ description │     │ rating_info{}   │  │
                  │ └─────────────┘     │ stats{}         │  │
                  │                     └─────────────────┘  │
                  │                              ↑           │
                  │     ┌──────────────────────┐ │           │
                  │     │       Match          │ │           │
                  │     ├──────────────────────┤ │           │
                  │     │ id (PK)              │ │           │
                  │     │ game_id (FK)         │─┘           │
                  │     │ played_at            │             │
                  │     │ match_metadata{}     │             │
                  │     └──────────────────────┘             │
                  │              │                           │
                  │              ↓                           │
                  │     ┌──────────────────────┐             │
                  └────→│  MatchParticipant    │─────────────┘
                        ├──────────────────────┤
                        │ id (PK)              │
                        │ match_id (FK)        │
                        │ player_id (FK)       │
                        │ team_id              │
                        │ outcome{}            │
                        │ rating_info_before{} │
                        │ rating_info_change{} │
                        └──────────────────────┘
```

**JSON Field Schemas:**

`GameProfile.rating_info`:
```json
{
  "rating": 1500.0,
  "rd": 350.0,
  "vol": 0.06
}
```

`GameProfile.stats`:
```json
{
  "matches_played": 42,
  "wins": 25,
  "losses": 17,
  "win_rate": 0.595
}
```

`MatchParticipant.outcome`:
```json
// Binary
{"result": "win"}  // or "loss", "draw"

// Ranked
{"rank": 1}  // 1st place

// Scored
{"result": "win", "score": 11, "opponent_score": 8}
```

`Match.match_metadata`:
```json
{
  "type": "Official Pickleball Rules",
  "final_score": "11-8",
  "source": "Historical Import 2025-11-09"
}
```

### API Design

**RESTful Conventions:**
- Resource-based URLs: `/players`, `/games`, `/matches`
- HTTP methods: GET (read), POST (create), PUT (update), DELETE (remove)
- Status codes: 200 (success), 201 (created), 204 (no content), 404 (not found)
- JSON request/response bodies

**Current Endpoints:**
```
Players:
  POST   /players/                Create player
  GET    /players/                List all players
  GET    /players/{id}            Get single player
  PUT    /players/{id}            Update player
  DELETE /players/{id}            Delete player

Games:
  POST   /games/                  Create game
  GET    /games/                  List all games
  GET    /games/{id}              Get single game
  PUT    /games/{id}              Update game
  DELETE /games/{id}              Delete game

Matches:
  POST   /matches/                Create match (triggers rating calc)
  GET    /matches/                List all matches
  GET    /matches/{id}            Get single match
  DELETE /matches/{id}            Delete match
```

**Planned Endpoints:**
```
Leaderboard:
  GET    /games/{id}/leaderboard  Get ranked players for game
         ?sort=rating|wins|winrate
         ?limit=50

Player Stats:
  GET    /players/{id}/stats      Get player statistics
  GET    /players/{id}/matches    Get player's match history
         ?game_id=1&limit=20

Matchmaking:
  POST   /matchmaking/generate    Generate balanced teams
         Body: {game_id, player_ids[], constraints?}
         Response: [{teams: [[id...], [id...]], fairness: 0.95}, ...]

Health:
  GET    /health                  Health check for monitoring
```

---

## Development Guidelines

### Code Quality Standards

**Testing Requirements:**
- Unit tests for all business logic functions
- Integration tests for API endpoints
- Test coverage target: >80%
- All async code tested with pytest-asyncio
- Use in-memory SQLite for test isolation

**Documentation Standards:**
- Docstrings for all public functions/classes
- Type hints on all function signatures
- Complex algorithms explained in comments
- README updated for new features

**Code Review Process:**
- All changes via pull request
- At least one review before merge (even for solo development - use self-review checklist)
- CI must pass before merge
- Squash merge for clean history

**Linting/Formatting:**
- Ruff for linting (E, F, I rules)
- Ruff for formatting (88 char line length, double quotes)
- Mypy for type checking (strict mode)
- Pre-commit hooks enforce on every commit

### Git Workflow

**Branching Strategy:**
```
main (protected)
  └── feature/matchmaking-algorithm
  └── feature/frontend-leaderboard
  └── fix/rating-edge-case
  └── docs/api-examples
```

**Branch Naming:**
- `feature/` - New functionality
- `fix/` - Bug fixes
- `refactor/` - Code improvements without behavior change
- `docs/` - Documentation only
- `chore/` - Maintenance (dependencies, CI, etc.)

**Commit Message Convention:**
```
type(scope): short description

Longer explanation if needed.

Closes #123
```

Types: feat, fix, docs, refactor, test, chore

**PR Requirements:**
- Descriptive title and description
- Link to related issue(s)
- Screenshots for UI changes
- Test coverage maintained or improved
- No linting/type errors

### Production Readiness Checklist

- [ ] Comprehensive test coverage (>80%)
- [ ] API documentation (OpenAPI/Swagger) - auto-generated by FastAPI
- [ ] User documentation (README, guides)
- [ ] Deployment automation (CI/CD)
- [ ] Monitoring and logging (Sentry, structured logs)
- [ ] Security audit completed (OWASP top 10 review)
- [ ] Performance benchmarks met (<200ms API, <3s frontend load)
- [ ] Accessibility standards met (WCAG 2.1 AA for frontend)
- [ ] Mobile responsive design
- [ ] Error handling covers all edge cases
- [ ] Database migrations tested on production-like data
- [ ] Rollback procedure documented

---

## Open Source Considerations

### Repository Setup

**Files to Create:**
- [x] LICENSE (MIT - already present)
- [x] README.md (needs expansion)
- [ ] CONTRIBUTING.md
- [ ] CODE_OF_CONDUCT.md
- [ ] .github/ISSUE_TEMPLATE/bug_report.md
- [ ] .github/ISSUE_TEMPLATE/feature_request.md
- [ ] .github/PULL_REQUEST_TEMPLATE.md
- [ ] .github/workflows/ci.yml
- [ ] .github/FUNDING.yml (optional)

### Documentation Requirements

**Installation Guide:**
- Prerequisites (Python, Node.js, Docker)
- Step-by-step setup for development
- Environment variable reference
- Database initialization
- Running tests

**Configuration Guide:**
- All environment variables explained
- Rating engine configuration
- Matchmaking algorithm parameters
- Production vs. development settings

**API Documentation:**
- OpenAPI spec (auto-generated)
- Example requests/responses
- Authentication (if added)
- Rate limits (if added)

**Architecture Documentation:**
- System overview diagram
- Database schema
- Rating algorithm explanation
- Matchmaking algorithm paper

**User Guide:**
- Recording matches
- Understanding ratings
- Using matchmaking
- Viewing statistics

**Developer Guide:**
- Project structure
- Adding new rating engines
- Adding new API endpoints
- Testing strategies

### Community Building

**Strategies for Attracting Contributors:**
1. Well-labeled "good first issue" tags
2. Clear CONTRIBUTING.md with setup instructions
3. Responsive to issues and PRs
4. Recognition in README for contributors
5. Detailed issue descriptions with context

**GitHub Profile Optimization:**
- Detailed "About" section with live demo link
- Topics/tags: rating-system, matchmaking, fastapi, react, glicko2, sports-analytics
- Social preview image (screenshot or logo)
- Pinned on profile

**Portfolio Presentation:**
- Featured in GitHub profile README
- Deployed demo with sample data
- Blog post explaining the project
- Video walkthrough of features

---

## Timeline & Milestones

### Realistic Schedule (3-6 hours/week)

| Phase | Duration | Hours | Target Completion |
|-------|----------|-------|-------------------|
| Phase 0: Foundation Refactoring | 20-40 weeks | 122 | Week 40 |
| Phase 1: Matchmaking + Match Updates | 12-20 weeks | 79-89 | Week 60 |
| Phase 2: Frontend | 10-21 weeks | 50-64 | Week 81 |
| Phase 3: Deployment | 6-13 weeks | 30-38 | Week 94 |
| Phase 4: Documentation | 5-12 weeks | 28-35 | Week 106 |

**Total: ~309-348 hours over 18-24 months**

*Note: Phase 0 is significantly larger than originally estimated due to critical technical debt. This investment is necessary—building features on a broken foundation would multiply problems later.*

**Phase 0 Breakdown:**
| Sub-Phase | Hours | Can Parallelize? |
|-----------|-------|------------------|
| 0A: Critical Infrastructure | 10 | No - do first |
| 0B: Data Layer | 50 | Yes, after 0A |
| 0C: API Layer | 27 | Yes, after 0A |
| 0D: Test Coverage | 22 | Yes, alongside 0B/0C |
| 0E: Dev Environment | 13 | Yes, anytime |

**Phase 1 now includes Match Update Cascade:**
| Component | Hours |
|-----------|-------|
| Original matchmaking work | 39-49 |
| Match update cascade implementation | 40 |
| Total | 79-89 |

### Key Milestones

1. **Backend API Complete** - End of Phase 0
   - All planned endpoints functional
   - Leaderboard and stats available
   - Docker development environment working

2. **Matchmaking MVP** - End of Phase 1
   - Algorithm generates balanced teams
   - API endpoint available
   - Algorithm documented

3. **Frontend Alpha** - Mid-Phase 2
   - Match recording works end-to-end
   - Leaderboard displays correctly
   - Deployed to staging environment

4. **Full MVP** - End of Phase 2
   - All four user flows complete
   - Responsive design working
   - Ready for friend group testing

5. **Production Launch** - End of Phase 3
   - Deployed to production
   - CI/CD pipeline operational
   - Error tracking in place

6. **Open Source Ready** - End of Phase 4
   - Comprehensive documentation
   - Contributor-friendly repository
   - Portfolio presentation complete

### Contingency Planning

**Buffer Time:**
- Each phase includes ~20% buffer in estimates
- Phase 3 and 4 can be compressed if behind schedule
- MVP can be redefined to ship faster

**Risk Mitigation:**

| Risk | Impact | Mitigation |
|------|--------|------------|
| Matchmaking algorithm complexity | High | Start simple, iterate |
| Frontend learning curve | Medium | Follow tutorials, use component libraries |
| Deployment issues | Medium | Use PaaS (Railway/Render) to minimize DevOps |
| Scope creep | High | Strict MVP definition, defer features |
| Burnout | High | Sustainable 3-6 hrs/week, celebrate milestones |

---

## Success Metrics

### Project Completion Criteria

- [ ] All MVP features implemented and tested
- [ ] Production deployment successful and stable
- [ ] Documentation complete and accessible
- [ ] Code quality standards met (>80% coverage, no linting errors)
- [ ] Repository ready for public consumption
- [ ] At least one full end-to-end usage session with friends

### Portfolio/Resume Impact

**Resume Bullet Point:**
> Designed and built RankForge, a full-stack rating and matchmaking platform using FastAPI, React, PostgreSQL, and TypeScript. Implemented Glicko-2 algorithm and novel matchmaking system using skill distribution superposition and simulated annealing. Deployed as open-source with comprehensive documentation.

**LinkedIn Presentation:**
- Featured project with live demo link
- Skills highlighted: Python, TypeScript, React, FastAPI, Algorithm Design, Data Science
- Engagement through posts about development journey

**GitHub Profile:**
- Pinned repository with star count
- Active commit history showing consistency
- Professional README with screenshots

**Technical Interview Material:**
- Algorithm design decisions
- System architecture trade-offs
- Testing strategies
- Production deployment experience

### User Engagement Goals

**Friend Group Adoption:**
- Target: 5-10 active users among friends
- Target: 20+ matches recorded per month
- Target: Weekly matchmaking usage for game nights

**Feature Adoption:**
- 100% of matches recorded through app (vs. manual tracking)
- 80%+ of sessions use matchmaking feature
- Players check leaderboard at least weekly

---

## Resources & References

### Technical Resources

**Rating Systems:**
- [Glicko-2 Paper (Glickman)](http://www.glicko.net/glicko/glicko2.pdf)
- [Wikipedia: Glicko Rating System](https://en.wikipedia.org/wiki/Glicko_rating_system)
- [TrueSkill Paper (Microsoft)](https://www.microsoft.com/en-us/research/publication/trueskill-a-bayesian-skill-rating-system/)

**FastAPI:**
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Tutorial](https://docs.sqlalchemy.org/en/20/tutorial/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)

**React/Frontend:**
- [React Documentation](https://react.dev/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/)
- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
- [React Query Documentation](https://tanstack.com/query/latest)
- [Vite Documentation](https://vitejs.dev/guide/)

**Deployment:**
- [Railway Documentation](https://docs.railway.app/)
- [Render Documentation](https://render.com/docs)
- [Docker Documentation](https://docs.docker.com/)

### Similar Projects

- [openskill.js](https://github.com/philihp/openskill.js) - Rating library implementing Weng-Lin model
- [lichess.org](https://github.com/lichess-org/lila) - Open source chess platform with Glicko-2
- [trueskill](https://github.com/sublee/trueskill) - Python implementation of TrueSkill
- [ratings](https://github.com/atomicjolt/ratings) - Multi-algorithm rating library

### Tools & Services

**Development:**
- [VS Code](https://code.visualstudio.com/) - Editor
- [Insomnia](https://insomnia.rest/) / [Postman](https://www.postman.com/) - API testing
- [TablePlus](https://tableplus.com/) - Database GUI

**Deployment:**
- [Railway](https://railway.app/) - Backend hosting (free tier available)
- [Render](https://render.com/) - Alternative backend hosting
- [Vercel](https://vercel.com/) - Frontend hosting
- [Netlify](https://www.netlify.com/) - Alternative frontend hosting
- [Supabase](https://supabase.com/) - Managed PostgreSQL (free tier)

**CI/CD:**
- [GitHub Actions](https://github.com/features/actions) - CI/CD pipelines

**Monitoring:**
- [Sentry](https://sentry.io/) - Error tracking (free tier)

---

## Next Immediate Actions

Start here. These are the first tasks to tackle in order. **Phase 0A is critical and must be completed first.**

### Week 1-2: Critical Infrastructure (Phase 0A)

1. **Externalize Database Configuration** (1 hour)
   - Move database URL from [session.py](src/rankforge/db/session.py) to environment variable
   - Create `.env.example` with `DATABASE_URL` template
   - Test with both SQLite and PostgreSQL connection strings

2. **Add Connection Pool Configuration** (2 hours)
   - Configure `pool_size`, `max_overflow`, `pool_pre_ping` in engine creation
   - Add FastAPI lifespan event for connection cleanup
   - Test under simulated load

3. **Fix Transaction Atomicity in match_service** (4 hours)
   - Rewrite `process_new_match()` to keep match creation and rating update in single transaction
   - Move `glicko2_engine.update_ratings_for_match()` call BEFORE commit
   - Add try-except with rollback on any failure
   - Write test that verifies rollback on rating engine failure

4. **Add Error Handling to get_db()** (1 hour)
   - Wrap session yield in try-except
   - Explicit rollback on exception
   - Add logging for database errors

### Week 3-4: Begin Data Layer Refactoring (Phase 0B)

5. **Add Database Indexes** (2 hours)
   - Add indexes to foreign key columns in models.py
   - Create Alembic migration
   - Test query performance improvement

6. **Standardize Rating Info Keys** (3 hours)
   - Choose standard: `rating`, `rd`, `sigma`
   - Update glicko2_engine.py, match_service.py, and all existing data
   - Create migration script for existing database
   - Update all tests

7. **Create Typed Schemas for JSON Fields** (3 hours)
   - Create `RatingInfo` TypedDict/Pydantic model
   - Create `BinaryOutcome` and `RankedOutcome` schemas
   - Update match.py schema to use discriminated union
   - Add validation tests

### Parallel: Development Environment

8. **Set Up Docker Development** (4 hours)
   - Create Dockerfile for backend
   - Create docker-compose.yml with app + PostgreSQL
   - Document docker development workflow in README
   - Test full workflow: build, migrate, run, test

---

**Document Version:** 1.0
**Last Updated:** 2025-12-19
**Next Review:** After Phase 0 completion

---

*This document should be treated as a living plan. Review and update after each phase completion or when priorities change significantly.*
