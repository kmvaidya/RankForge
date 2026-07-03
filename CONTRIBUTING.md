# Contributing to RankForge

Thanks for your interest in contributing! This guide gets you productive quickly.

## Development Setup

**Backend** (Python 3.10+):

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   |   macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
alembic upgrade head
uvicorn rankforge.main:app --reload --app-dir src
```

**Frontend** (Node 20+):

```bash
cd frontend
npm install
npm run dev
```

Or run everything with Docker: `docker compose up -d` (see the README).

## Before You Submit

All of these must pass — CI enforces them:

```bash
# Backend
ruff check src tests
ruff format --check src tests
mypy src
pytest

# Frontend
cd frontend && npm run lint && npm run build
```

Pre-commit hooks run the backend checks automatically on commit.

## Guidelines

- **Branches:** `feature/…`, `fix/…`, `refactor/…`, `docs/…`, `chore/…`
- **Commits:** `type(scope): short description` (e.g. `feat(matchmaking): add role constraints`)
- **Tests:** new behavior needs tests; bug fixes need a regression test
- **Types:** full type hints on all function signatures (mypy must stay clean)
- **Docstrings:** public functions and classes get docstrings; explain *why* for anything non-obvious

## Architecture Primer

- `src/rankforge/api/` — thin FastAPI routers; no business logic
- `src/rankforge/services/` — business logic; services own transaction boundaries (commit/rollback)
- `src/rankforge/rating/` — rating engines; flush but never commit; raise instead of silently skipping
- Rating engines are pluggable: implement `update_ratings_for_match(db, match)` and register it in `rankforge/rating/__init__.py`
- Match corrections replay history forward — see `services/recalculation_service.py` and `docs/matchmaking-algorithm.md` for the matchmaking math

## Reporting Issues

Use the issue templates. For bugs, include reproduction steps and the relevant
request/response bodies (the `X-Request-ID` response header helps correlate logs).
