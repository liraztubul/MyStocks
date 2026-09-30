# MyStocks — Architecture & Milestone Plan

Living reference for whoever (Claude Code included) picks up work on this repo. Read this before starting a new milestone.

## Decisions locked in

- Multi-currency: schema stores `currency` per transaction/user now; MVP hardcodes `"USD"` everywhere; real FX conversion is Phase 2 (with TASE/ILS).
- Repo: monorepo (`backend/` + `frontend/`).
- Deploy target: TBD at M7, likely Fly.io or Railway.
- Auth: argon2 password hashing, self-signup open, JWT in an httpOnly/secure/samesite=lax cookie, ~30min expiry, no refresh flow (documented MVP limitation).
- Transactions: `asset_type` is `stock | crypto`. `symbol` is free text (no exchange validation until M4's market-data provider). `executed_at` is user-supplied, not defaulted to now.
- Money/quantity: `Numeric(28,10)` in Postgres, `Decimal` end to end in Python, JSON in/out as strings (never floats) — see `backend/app/schemas/decimal.py`.
- Oversell validation: replays a symbol's trade history in `executed_at` order (buys before sells at the same timestamp), not just a final-totals comparison — catches backdated sells. See `backend/app/domain/holdings.py`. Writes are serialized per-user via `SELECT ... FOR UPDATE` on the user row.

## Repo structure

```
MyStocks/
├── backend/app/{api,core,db,domain,market_data,schemas}/
├── backend/tests/{unit,integration}/
├── frontend/src/{api,components,pages,hooks}/
├── docker-compose.yml, .env.example
├── docs/architecture-plan.md   (this file)
└── ROADMAP.md                  (phase 2/3/4 hooks + known MVP gaps)
```

## Milestone status

| # | Milestone | Status |
|---|---|---|
| M0 | Skeleton (FastAPI + React scaffold, docker-compose, CI) | Done, committed |
| M1 | Auth (register/login/JWT cookie) | Done, verified live |
| M2 | Transactions CRUD + oversell validation | Done, verified live |
| M3 | P/L engine (avg cost basis, unrealized/realized P/L) | Next |
| M4 | Market data provider (yfinance + CoinGecko, TTL cache) | Not started |
| M5 | Portfolio dashboard | Not started |
| M6 | Price chart | Not started |
| M7 | Polish + deploy | Not started |

## The 3 riskiest technical decisions (from initial planning)

1. **Market data providers** — yfinance (unofficial, can break) + CoinGecko, both behind a `MarketDataProvider` interface so swapping providers later is a one-adapter change.
2. **Cost-basis correctness** — the module most worth heavy testing (property-based tests earn their cost here). M2's `domain/holdings.py` already sets the pattern: pure functions, no DB/FastAPI imports, tested in isolation.
3. **JWT strategy** — short-lived cookie, no refresh flow in MVP; documented limitation, not silently skipped.

## Known MVP gaps (see ROADMAP.md for the full list)

Deleting a transaction doesn't retroactively re-validate the rest of that symbol's history; USD only; free-text symbols; no transaction edit UI yet (PATCH exists, tested, no frontend for it).
