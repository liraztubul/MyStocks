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
cp .env.example .env
# then set JWT_SECRET_KEY in .env:
python -c "import secrets; print(secrets.token_urlsafe(48))"
# and FINNHUB_API_KEY (free, no card: https://finnhub.io/register) for stock search/quotes.
# Crypto (CoinGecko) works without a key.
```

### Backend (without Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
docker compose up -d postgres    # or any Postgres matching the POSTGRES_* vars in .env
alembic upgrade head
uvicorn app.main:app --reload    # http://localhost:8000/api/health
```

Tests and lint (integration tests need Postgres running; they create and use a separate `<POSTGRES_DB>_test` database):

```bash
pytest
ruff check . && ruff format --check .
```

Real-network tests against Finnhub/CoinGecko are excluded by default (so CI can't flake on them). Run them explicitly with `pytest -m live_network`; the Finnhub ones skip unless `FINNHUB_API_KEY` is set.

New migration after changing a model: `alembic revision --autogenerate -m "..."`, then review the generated file.

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
- The backend runs `alembic upgrade head` on startup.

## Status

M4 (market data) — auth, a transaction ledger with oversell validation, and symbol search + price autofill via Finnhub/CoinGecko. See [ROADMAP.md](ROADMAP.md) for milestones and known limitations.
