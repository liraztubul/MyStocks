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

## Assumptions

How P/L is calculated (see `backend/app/domain/pnl.py`):

- **Average cost basis.** The average moves only on buys: `new_avg = (held_qty * avg + buy_qty * price + buy_fee) / (held_qty + buy_qty)`. Selling never changes it. When a position is sold down to zero, its average resets, so a later re-buy starts fresh. The calculation sits behind a strategy interface, so FIFO can be added later.
- **Fees.** A buy's fee is added to its cost basis. A sell's fee is subtracted from its proceeds.
- **Realized P/L** per sell = `(sell_price - average_cost) * quantity - sell_fee`.
- **Unrealized P/L** = `(current_price - average_cost) * held_quantity`. The % is relative to the cost basis of what's still held, fees included.
- **Replay order.** Each symbol's trades are replayed in `executed_at` order, with buys before sells at the same timestamp. This is the same rule the oversell check uses.
- **USD only.** All amounts are USD and there is no currency conversion.
- **Precision.** The engine never rounds: it works in a 60-significant-digit Decimal context. The API rounds amounts to 10 decimal places and percentages to 4 (half-even), and the UI rounds again for display.
- **Prices.** Live prices are cached for 60 seconds. If a provider is down or rate-limited, the last known price is shown, marked stale with its original timestamp. A holding that has never been priced shows no market value rather than failing the whole portfolio.

## Status

M3 (P/L engine) — auth, a transaction ledger with oversell validation, symbol search + price autofill via Finnhub/CoinGecko, and average-cost holdings with realized/unrealized P/L. See [ROADMAP.md](ROADMAP.md) for milestones and known limitations.
