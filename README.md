# RankForge

[![CI](https://github.com/kmvaidya/RankForge/actions/workflows/ci.yml/badge.svg)](https://github.com/kmvaidya/RankForge/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A modern, full-stack rating and matchmaking system designed to handle any competitive game. RankForge provides a flexible architecture for tracking player ratings, match histories, and generating balanced teams for any number of players and team structures.

## Core Features

- **Game Agnostic:** Unified database schema handles 1v1 win/loss, team-based, multi-team ranked, and free-for-all formats
- **Flexible Rating System:** Pluggable rating algorithms per game (Glicko-2 implemented), with per-game tuning via `rating_config`: system constant (`tau`), score-margin weighting, minimum rating swing, inactivity RD growth, and season RD resets
- **Match Prediction & Honest Evaluation:** Win probabilities for any team split from the engine's own expected-score math (`POST /games/{id}/predict`), and a walk-forward calibration report (`GET /games/{id}/calibration`) that scores the ratings against real history — Brier, accuracy, expected calibration error, reliability bins
- **Balanced Matchmaking:** Novel algorithm using skill-distribution superposition and simulated annealing — see [docs/matchmaking-algorithm.md](docs/matchmaking-algorithm.md)
- **Match Corrections:** Fix historical matches (wrong winner, players, or date); all subsequent ratings — including season boundaries and inactivity growth — are replayed deterministically, with optimistic-locking protection
- **Seasons:** Boundary timestamps that re-open the ladder (RD reset) while preserving skill, with separate season/career records
- **Web UI:** React + TypeScript single-page app — leaderboards (with a conservative rating−2·RD view), two-tap match recording with live pre-match odds and upset callouts, matchmaking, live session runner, and player profiles with uncertainty-band rating charts and partner/rival chemistry
- **Weighted Matches:** Any match can carry more or less rating information (`match_metadata.weight`), optionally scaled further by score margin
- **Offline Parameter Tuning:** `python -m rankforge.tools.tune` replays a game's real history across a parameter grid and reports Brier/drift per combination
- **Anonymous Players:** Support for one-time anonymous participants in matches
- **Feature Flags:** `RANKFORGE_FEATURES` gates deployment-specific UI (match weights, session mode) without forking the generic core
- **Docker Ready:** Production-ready containerization with PostgreSQL 16 and an nginx-served frontend
- **Modern Async Stack:** FastAPI + SQLAlchemy 2.0 async with full type hints
- **Comprehensive Testing:** 300+ tests with pytest-asyncio; CI via GitHub Actions

Architecture deep-dive: [docs/architecture.md](docs/architecture.md)

## Tech Stack

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **Frontend:** [React 19](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/) + [Vite](https://vitejs.dev/) + [Tailwind CSS 4](https://tailwindcss.com/)
- **Database:** [PostgreSQL 16](https://www.postgresql.org/) (Docker) / [SQLite](https://www.sqlite.org/) (local dev)
- **ORM:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Async)
- **Migrations:** [Alembic](https://alembic.sqlalchemy.org/)
- **Containerization:** Docker + Docker Compose
- **Code Quality:** [Ruff](https://github.com/astral-sh/ruff) + [Mypy](http://mypy-lang.org/) + [oxlint](https://oxc.rs/)

---

## Quick Start

### Option 1: Docker (Recommended)

The fastest way to get RankForge running with PostgreSQL.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
# Clone the repository
git clone https://github.com/kmvaidya/RankForge.git
cd RankForge

# Copy environment file (optional - defaults work out of box)
cp .env.example .env

# Start the services (API + PostgreSQL + web frontend)
docker compose up -d

# Run database migrations
docker compose run --rm migrations

# Verify it's running
curl http://localhost:8000/health
```

- **Web app:** [http://localhost:3000](http://localhost:3000)
- **API:** [http://localhost:8000](http://localhost:8000)
- **Interactive API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

### Option 2: Local Python Setup

For development without Docker, using SQLite.

**Prerequisites:** Python 3.10+, Git

```bash
# Clone the repository
git clone https://github.com/kmvaidya/RankForge.git
cd RankForge

# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -e .[dev]

# Set up pre-commit hooks
pre-commit install

# Run database migrations
alembic upgrade head

# Start the server
uvicorn rankforge.main:app --reload --app-dir src
```

The API is now available at [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Frontend Development

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173, proxies /api to the backend
```

See [frontend/README.md](frontend/README.md) for build and deployment details.

---

## API Reference

### Games

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/games/` | Create a new game |
| `GET` | `/games/` | List games (paginated) |
| `GET` | `/games/{id}` | Get game by ID |
| `PUT` | `/games/{id}` | Update a game |
| `DELETE` | `/games/{id}` | Delete a game |
| `GET` | `/games/{id}/leaderboard` | Get player rankings for a game |
| `POST` | `/games/{id}/predict` | Win probabilities for a hypothetical team split |
| `GET` | `/games/{id}/calibration` | Walk-forward prediction-quality report (Brier, accuracy, ECE) |
| `GET` | `/games/{id}/health` | Rating-inflation monitor (mean rating, drift from 1500) |
| `GET` | `/games/{id}/seasons` | List season boundaries |
| `POST` | `/games/{id}/seasons` | Start a new season (RD reset, season stats zeroed) |
| `POST` | `/games/{id}/recalculate` | Rebuild the game's full rating history and stats |

### Players

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/players/` | Create a new player |
| `GET` | `/players/` | List players (paginated) |
| `GET` | `/players/{id}` | Get player by ID |
| `PUT` | `/players/{id}` | Update a player |
| `DELETE` | `/players/{id}` | Delete a player |
| `GET` | `/players/{id}/stats` | Get player statistics across all games |
| `GET` | `/players/{id}/chemistry` | Partner & head-to-head records (confidence-adjusted rates) |
| `GET` | `/players/{id}/matches` | Get player match history |

### Matches

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/matches/` | Create a match and process ratings |
| `GET` | `/matches/` | List matches (paginated, filterable) |
| `GET` | `/matches/{id}` | Get match by ID with participants |
| `PUT` | `/matches/{id}` | Correct a match; recalculates all affected ratings (optimistic locking via `expected_version`) |
| `DELETE` | `/matches/{id}` | Soft-delete a match and recalculate subsequent ratings |

### Matchmaking

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/matchmaking/generate` | Generate balanced team configurations (fairness-ranked, supports together/apart constraints) |

### Health Check & Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | API health status |
| `GET` | `/config` | Deployment feature flags for the frontend |

**Full API documentation:** Available at `/docs` (Swagger UI) or `/redoc` when the server is running.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./rankforge.db` | Database connection string |
| `POSTGRES_USER` | `rankforge` | PostgreSQL username (Docker) |
| `POSTGRES_PASSWORD` | `rankforge_dev` | PostgreSQL password (Docker) |
| `POSTGRES_DB` | `rankforge` | PostgreSQL database name (Docker) |
| `DB_POOL_SIZE` | `20` | Connection pool size (PostgreSQL only) |
| `DB_MAX_OVERFLOW` | `10` | Max overflow connections (PostgreSQL only) |
| `DB_POOL_RECYCLE` | `3600` | Connection recycle time in seconds |
| `DB_ECHO` | `false` | Enable SQL query logging |
| `CORS_ORIGINS` | localhost dev origins | Comma-separated origins allowed to call the API |
| `RANKFORGE_FEATURES` | (empty) | Comma-separated feature flags (`match_weights`, `session_mode`) |
| `MATCH_UPDATE_MAX_AGE_DAYS` | `0` (unlimited) | Reject corrections to matches older than this |
| `API_PORT` | `8000` | API port mapping (Docker) |
| `DB_PORT` | `5432` | PostgreSQL port mapping (Docker) |
| `WEB_PORT` | `3000` | Web frontend port mapping (Docker) |

---

## Docker Commands Reference

```bash
# Start services (detached)
docker compose up -d

# View logs
docker compose logs -f api

# Run migrations
docker compose run --rm migrations

# Stop services
docker compose down

# Stop and remove volumes (reset database)
docker compose down -v

# Rebuild after code changes
docker compose build api

# Run tests in container
docker compose run --rm api pytest

# Production mode (multiple workers, no hot reload)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Running Tests

```bash
# Local (with virtual environment activated)
pytest

# With coverage
pytest --cov=rankforge

# Specific test file
pytest tests/test_api_matches.py

# Docker
docker compose run --rm api pytest
```

---

## Project Structure

```
RankForge/
├── src/
│   ├── alembic/                  # Database migrations
│   │   └── versions/             # Migration scripts
│   └── rankforge/
│       ├── api/                  # FastAPI route handlers
│       │   ├── game.py           # Games + leaderboard + recalculate
│       │   ├── match.py          # Matches incl. correction (PUT)
│       │   ├── matchmaking.py    # Balanced team generation
│       │   └── player.py         # Players + stats + history
│       ├── db/                   # Database layer
│       │   ├── models.py         # SQLAlchemy models
│       │   └── session.py        # Async session management
│       ├── middleware/           # Logging + security headers
│       ├── rating/               # Rating engines (Glicko-2, dummy)
│       ├── schemas/              # Pydantic schemas
│       ├── services/             # Business logic
│       │   ├── match_service.py          # Create/update/delete matches
│       │   ├── matchmaking_service.py    # Fairness search
│       │   ├── prediction_service.py     # Win probs + calibration report
│       │   ├── recalculation_service.py  # Forward rating replay
│       │   ├── season_service.py         # Season boundaries & RD resets
│       │   └── stats_service.py          # Win/loss stats + chemistry
│       ├── tools/                # Offline utilities (rating tuner)
│       └── main.py               # FastAPI app entry point
├── frontend/                     # React + TypeScript + Vite SPA (PWA)
├── integrations/discord-bot/     # /rank slash-command bot (REST client)
├── tests/                        # Test suite (300+ tests)
├── docs/                         # Algorithm & architecture docs
├── .github/workflows/ci.yml     # CI: lint, types, tests, builds
├── docker-compose.yml            # Docker services (dev)
├── docker-compose.prod.yml       # Production overrides
├── Dockerfile                    # Backend multi-stage build
├── alembic.ini                   # Alembic configuration
└── pyproject.toml                # Project dependencies
```

---

## Development

### Code Quality

```bash
# Lint check
ruff check src tests

# Auto-fix lint issues
ruff check --fix src tests

# Format code
ruff format src tests

# Type check
mypy src
```

### Database Migrations

```bash
# Generate migration after model changes
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
