# RankForge

A modern, full-stack rating and matchmaking system designed to handle any competitive game. RankForge provides a flexible architecture for tracking player ratings, match histories, and generating balanced teams for any number of players and team structures.

## Core Features

- **Game Agnostic:** Unified database schema handles 1v1 win/loss, team-based, and multi-outcome formats
- **Flexible Rating System:** Pluggable rating algorithms per game (Glicko-2 implemented, Elo-ready)
- **Anonymous Players:** Support for one-time anonymous participants in matches
- **Docker Ready:** Production-ready containerization with PostgreSQL 16
- **Modern Async Stack:** FastAPI + SQLAlchemy 2.0 async with full type hints
- **Comprehensive Testing:** 160+ tests with pytest-asyncio

## Tech Stack

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **Database:** [PostgreSQL 16](https://www.postgresql.org/) (Docker) / [SQLite](https://www.sqlite.org/) (local dev)
- **ORM:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Async)
- **Migrations:** [Alembic](https://alembic.sqlalchemy.org/)
- **Containerization:** Docker + Docker Compose
- **Code Quality:** [Ruff](https://github.com/astral-sh/ruff) + [Mypy](http://mypy-lang.org/)

---

## Quick Start

### Option 1: Docker (Recommended)

The fastest way to get RankForge running with PostgreSQL.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
# Clone the repository
git clone https://github.com/your-username/RankForge.git
cd RankForge

# Copy environment file (optional - defaults work out of box)
cp .env.example .env

# Start the services
docker compose up -d

# Run database migrations
docker compose run --rm migrations

# Verify it's running
curl http://localhost:8000/health
```

The API is now available at [http://localhost:8000](http://localhost:8000)

**Interactive API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

### Option 2: Local Python Setup

For development without Docker, using SQLite.

**Prerequisites:** Python 3.10+, Git

```bash
# Clone the repository
git clone https://github.com/your-username/RankForge.git
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

### Players

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/players/` | Create a new player |
| `GET` | `/players/` | List players (paginated) |
| `GET` | `/players/{id}` | Get player by ID |
| `PUT` | `/players/{id}` | Update a player |
| `DELETE` | `/players/{id}` | Delete a player |
| `GET` | `/players/{id}/stats` | Get player statistics across all games |
| `GET` | `/players/{id}/matches` | Get player match history |

### Matches

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/matches/` | Create a match and process ratings |
| `GET` | `/matches/` | List matches (paginated, filterable) |
| `GET` | `/matches/{id}` | Get match by ID with participants |
| `DELETE` | `/matches/{id}` | Delete a match |

### Health Check

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | API health status |

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
| `API_PORT` | `8000` | API port mapping (Docker) |
| `DB_PORT` | `5432` | PostgreSQL port mapping (Docker) |

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
│   ├── alembic/              # Database migrations
│   │   └── versions/         # Migration scripts
│   └── rankforge/
│       ├── api/              # FastAPI route handlers
│       │   ├── game.py       # Game endpoints
│       │   ├── match.py      # Match endpoints
│       │   └── player.py     # Player endpoints
│       ├── db/               # Database layer
│       │   ├── models.py     # SQLAlchemy models
│       │   └── session.py    # Async session management
│       ├── middleware/       # Request/response middleware
│       ├── rating/           # Rating algorithms
│       │   └── glicko2.py    # Glicko-2 implementation
│       ├── schemas/          # Pydantic schemas
│       ├── services/         # Business logic
│       └── main.py           # FastAPI app entry point
├── tests/                    # Test suite (160+ tests)
├── scripts/                  # Import/utility scripts
├── docker-compose.yml        # Docker services (dev)
├── docker-compose.prod.yml   # Production overrides
├── Dockerfile                # Multi-stage build
├── alembic.ini               # Alembic configuration
└── pyproject.toml            # Project dependencies
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
