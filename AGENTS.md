# AGENTS.md

Gate.io Capital Preservation Bot — a full-stack trading system (Python/FastAPI backend + Next.js frontend) orchestrated with Docker Compose.

## Commands

### Backend (`backend/`)

```bash
# Install deps (editable, includes dev extras)
pip install -e '.[dev]'

# Lint — ruff only, no ESLint
ruff check app

# Typecheck — no mypy configured; rely on ruff + pytest for correctness
# Tests
pytest -q                      # all tests
pytest -k test_name            # single test by name
pytest backend/app/tests/test_health.py  # single file (from repo root)
```

- **Ruff config**: `line-length = 100`, `target-version = "py312"`.
- **Pytest config**: `asyncio_mode = "auto"`, `pythonpath = ["."]`.
- Tests are in `backend/app/tests/` (34 test files). No JS test framework exists.

### Frontend (`frontend/`)

```bash
# Install
npm ci || npm install

# Dev server
npm run dev        # http://localhost:3000

# Build (includes TS type-check via next build)
npm run build

# Lint — optional; project has no ESLint config, `next lint` may prompt interactively
npm run lint
```

- **No ESLint or Prettier config** — CI intentionally skips it (would hang).
- TypeScript strict mode is enabled.

### Docker

```bash
docker compose up -d          # postgres, redis, backend, scheduler, paper-worker, frontend
docker compose logs -f backend
```

Services: `postgres` (16-alpine), `redis` (7-alpine), `backend` (uvicorn :8000), `scheduler`, `paper-worker`, `frontend` (Next.js :3000). All read `.env` from repo root.

## Architecture

### Backend entry points

| Service | Command | Module |
|---------|---------|--------|
| API server | `uvicorn app.main:app --reload` | `backend/app/main.py` |
| Scheduler | `python -m app.workers.scheduler` | `backend/app/workers/scheduler.py` |
| Paper worker | `python -m app.workers.paper_worker` | `backend/app/workers/paper_worker.py` |

- FastAPI app mounts all routes under `/api/v1` via `app.api.v1.router`.
- Health: `/health` (liveness), `/health/ready` (DB check), `/metrics` (Prometheus).

### Backend module layout (`backend/app/`)

Core: `core/`, `db/`, `models/`, `schemas/`, `repositories/`, `api/`, `services/`, `main.py`.
Domain modules: `account/`, `auto_learning/`, `backtest/`, `execution_quality/`, `market_data/`, `market_data_quality/`, `market_regime/`, `paper_trading/`, `portfolio/`, `reconciliation/`, `strategy_health/`, `strategy_research/`, `walkforward/`, `workers/`.

### Frontend

Next.js 15 / React 19 / TailwindCSS / Recharts + Plotly. Pages mirror backend domain modules under `frontend/app/`.

## Environment

- Copy `.env.example` to `.env` and fill in Gate.io API keys, `SECRET_KEY`, `FERNET_KEY`, JWT secrets.
- `DATABASE_URL` and `REDIS_URL` must point to the Docker services (host `postgres`/`redis` inside compose).
- No `opencode.json`, `CLAUDE.md`, or other AI instruction files exist.
- README is in Turkish.

## Conventions

- **No ESLint/Prettier** — code style enforced by ruff only on the backend.
- **No TypeScript strict config beyond `tsconfig.json`** — rely on `next build` for type-checking.
- **CI order**: `ruff check app` → `pytest -q` (backend), `npm run build` (frontend).
- **Python 3.12+ required** — `pyproject.toml` specifies `requires-python = ">=3.12"`.
- Tests use `pytest-asyncio` with auto mode; async tests don't need explicit decorators.
- API keys are encrypted at rest via Fernet (`FERNET_KEY`).
- The bot has a dual master-key activation safety gate (see README).
