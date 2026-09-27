# MyStocks

Personal portfolio tracker & investing assistant for stocks, ETFs, and crypto — logs transactions and derives holdings, cost basis, and P/L from them.

> Derives holdings and P/L from a transaction ledger, the same way `git log` derives working-tree state from commits.

Built as both a job-interview portfolio project and a tool for personal investment tracking.

## Stack

React + TypeScript (Vite) · Python + FastAPI · PostgreSQL · SQLAlchemy + Alembic · Docker Compose

## Repo layout

```
backend/    FastAPI app (app/), Alembic migrations, pytest suite
frontend/   Vite + React + TS app, served by nginx in Docker
docker-compose.yml   postgres + backend + frontend
```

## Setup

Prerequisites: Python 3.10+, Node 22+, and (optionally) Docker.

```bash
git clone https://github.com/liraztubul/MyStocks.git
cd MyStocks
cp .env.example .env   # then edit values if you like
```

### Backend (without Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload    # http://localhost:8000/api/health
```

Tests and lint:

```bash
pytest
ruff check . && ruff format --check .
```

### Frontend (without Docker)

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

The Vite dev server proxies `/api` to `http://localhost:8000`, so start the backend first. Other scripts: `npm run lint`, `npm run typecheck`, `npm run build`.

### Everything with Docker Compose

```bash
docker compose up --build
```

- Frontend: http://localhost:8080 (nginx proxies `/api` to the backend)
- Backend: http://localhost:8000/api/health
- Postgres: `localhost:5432`, data persisted in the `postgres_data` volume

## Status

M0 (skeleton) — health endpoint wired end to end, no domain logic yet.
