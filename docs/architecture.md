# RankForge Architecture

## System Overview

```
┌───────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + TS + Vite)                  │
│  Leaderboard │ Record Match │ Matchmaking │ Matches │ Profiles    │
└──────────────────────────────┬────────────────────────────────────┘
                        HTTP/REST (axios, /api)
┌──────────────────────────────┴────────────────────────────────────┐
│                        BACKEND (FastAPI)                          │
│  api/          routers: players, games, matches, matchmaking     │
│  services/     match_service │ matchmaking │ recalculation │ stats│
│  rating/       engine registry: glicko2 │ dummy │ (pluggable)     │
│  db/           SQLAlchemy 2.0 async models + session              │
│  middleware/   request logging (X-Request-ID) │ security headers  │
└──────────────────────────────┬────────────────────────────────────┘
                     PostgreSQL 16 (prod) / SQLite (dev)
```

## Layering Rules

- **API layer** (`api/`): request parsing, response shaping, HTTP status
  mapping. No business logic. Global exception handlers in `main.py` map the
  exception hierarchy (`exceptions.py`) to status codes: 404 / 409 / 422 / 500.
- **Service layer** (`services/`): business logic and **transaction
  ownership** — services commit or roll back; nothing below them does.
- **Rating layer** (`rating/`): pure rating math + persistence of
  `rating_info`. Engines flush but never commit, and raise instead of
  silently skipping. Registered in `rating/__init__.py`; a game's
  `rating_strategy` column selects the engine per match.
- **Stats** (`services/stats_service.py`): win/loss/draw counters live in
  `GameProfile.stats`, incremented on match creation and rebuilt from scratch
  after any history rewrite.

## Data Model

```
Player ──< GameProfile >── Game
   │            (rating_info, stats per game)
   │
   └──< MatchParticipant >── Match >── Game
          (team_id, outcome,
           rating_info_before, rating_info_change)
```

- **Player** — unique person across all games (soft-deletable; `is_anonymous`
  marks the shared "Unknown" player used for casual participants).
- **Game** — competitive context; owns the `rating_strategy`.
- **GameProfile** — one row per (player, game): current `rating_info`
  (`{rating, rd, vol}`) and cached `stats`.
- **Match** — one played instance: `played_at` (business time, indexed),
  flexible `match_metadata`, optimistic-locking `version`, soft-delete
  `deleted_at`.
- **MatchParticipant** — links players to matches with team assignment,
  outcome (`{result: win|loss|draw}` or `{rank: n}`), and the rating snapshot
  before/after — this snapshot is what makes history replay possible.

All tables carry `created_at`/`updated_at`; mutation-prone tables carry
`version` and `deleted_at` (mixins in `db/models.py`).

## Key Flows

### Recording a match (atomic)

```
POST /matches → match_service.process_new_match()
  validate participants (≥2, no dupes, ≥2 teams, players exist)
  create Match + MatchParticipants (flush, no commit)
  snapshot rating_info_before per participant
  dispatch to rating engine → new ratings + rating_info_change (flush)
  update win/loss stats
  COMMIT (everything or nothing)
```

### Correcting history (the cascade)

Editing or deleting a match invalidates every later rating. RankForge does
full forward recalculation (`services/recalculation_service.py`):

```
PUT/DELETE /matches/{id}
  check optimistic lock (expected_version)
  capture reset targets: each affected player's rating before their first
    match in the affected window (uses stored rating_info_before)
  apply the correction (mutate or soft-delete)
  reset affected profiles → replay window in (played_at, id) order
  rebuild stats from scratch for affected players
  COMMIT — a failure anywhere rolls back the entire correction
```

`POST /games/{id}/recalculate` runs the same replay over a game's entire
history — useful after bulk imports.

### Matchmaking

`POST /matchmaking/generate` models players as Gaussians N(rating, RD),
teams as their superposition, and searches partitions for outcomes closest
to a coin flip (exhaustive below ~20k partitions, simulated annealing
above). Full math: [matchmaking-algorithm.md](matchmaking-algorithm.md).

## Operational Notes

- **Config** is environment-driven (`.env`, see `.env.example`): database
  URL/pooling, CORS origins, match-update age limit.
- **Observability**: every request gets an `X-Request-ID` (logging
  middleware); structured logs throughout services.
- **Docker**: `docker compose up` runs PostgreSQL + API (hot reload) + web
  (nginx). The prod overlay removes reload, adds workers and resource
  limits. Migrations run as a one-shot service.
- **CI** (GitHub Actions): ruff + mypy + pytest, frontend lint + typed
  build, and both Docker images.

## Extension Points

- **New rating engine**: implement `update_ratings_for_match(db, match)`,
  register in `rating/__init__.py`, set a game's `rating_strategy` to its key.
- **New outcome shape**: extend the `Outcome` union in `schemas/match.py`
  and teach `stats_service.outcome_result` how to classify it.
- **External sync**: `ExternalSyncBatch`/`ExternalSyncRecord` track exports
  to systems like DUPR without schema changes per system.
