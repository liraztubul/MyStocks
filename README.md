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
- **Data delay.** The dashboard polls every 60 seconds (paused while the tab is hidden), on top of the 60-second cache, so a price can be about 2 minutes old plus any delay on the provider's side. Don't treat it as real-time.
- **Daily change** (see `backend/app/domain/daily_change.py`) is price-only (fees excluded) and is measured from a *reference point*:
  - **Stocks: since the previous close.** That's Finnhub's `pc`, for the session the latest quote belongs to. Before the market opens, that session is the last completed one, so the "previous close" can be days old (a Monday morning shows Friday's move). The UI shows which session.
  - **Crypto: rolling 24h.** CoinGecko only offers a 24-hour % change, not a change since a close; crypto never closes. The base price is derived from that % and labelled "rolling 24h", so stock and crypto changes aren't directly comparable.
  - Shares bought after the reference are measured from their **buy price**, not the reference. Shares sold after it count from the reference to the sell price.
  - The portfolio total covers **open positions only**: a position fully closed since the reference drops out (its realized P/L still counts). Missing or zero reference data shows as "—", never as 0.
- **Hosting.** Production runs on free tiers that sleep when idle; see [Deployment](#deployment) for cold starts and limits.
- **Not financial advice.** Market data comes from free third-party APIs (Finnhub, CoinGecko) under their free-tier terms. This is an educational and personal-tracking project; numbers may be delayed, incomplete or wrong.

## Deployment

MyStocks runs on free tiers: the static frontend on **Vercel**, the FastAPI container on **Render**, and Postgres on **Neon**. Everything except secrets is in the repo (`render.yaml`, `frontend/vercel.json`, `.github/workflows/`).

### Architecture and request flow

```
                         ┌──────────── Vercel (Hobby) ─────────────┐
 Browser ──── https ───▶ │ static SPA + security headers / CSP     │
  (cookie: httpOnly,     │ /api/*  → reverse proxy (up to 120 s)   │
   Secure, SameSite=Lax) │   adds  x-origin-secret: <secret>       │
                         │   sets  X-Forwarded-For: <visitor IP>   │
                         └──────────────────┬──────────────────────┘
                                            │ https
                         ┌──────────────────▼──────────────────────┐
                         │ Render free web service (Docker)        │
                         │ start: alembic upgrade head → uvicorn   │
                         │ rejects /api/* without the secret (403) │
                         │ /healthz  liveness, no DB (Render check)│
                         │ /readyz   SELECT 1                      │
                         └──────────────────┬──────────────────────┘
                                            │ direct connection, sslmode=require
                         ┌──────────────────▼──────────────────────┐
                         │ Neon Postgres (Free), suspends after 5m │
                         └─────────────────────────────────────────┘
  GitHub Actions: ci.yml (gates deploys) · backup.yml (daily encrypted pg_dump)
```

- **One origin, so the cookie just works.** The browser only ever talks to the Vercel domain. `/api/*` is proxied to Render, so the auth cookie is first-party, and `SameSite=Lax` plus `Secure` work with no CORS setup.
- **Render only trusts Vercel.** Vercel adds a shared secret header to every proxied request, and the API answers anything under `/api` without it with a generic 403. That also stops anyone bypassing Vercel to spoof `X-Forwarded-For`, which the rate limiter relies on.
- **CSRF defence in depth.** State-changing requests whose `Origin` isn't in `ALLOWED_ORIGINS` are refused, on top of SameSite.

### Cold starts (the normal case)

Render's free web service **spins down after 15 minutes without traffic** and takes **about a minute** to wake on the next request. MyStocks is deliberately **not** kept awake: no pinger, so it only uses instance hours while someone is actually using it.

- The first visit after idling waits about a minute. Vercel holds the request for up to 120 s, so it normally just completes slowly.
- The frontend shows *"Server is waking up, this can take about a minute"* once a request takes longer than 8 s. Queries retry automatically every 5 s for about 2 minutes on 502/503/504 or network errors.
- **The price cache is empty after every wake.** The live-quote and last-known-good caches are in memory, so they start empty. Until each symbol is fetched once, a provider hiccup shows that symbol as *unpriced* rather than stale.
- Neon suspends on its own after 5 minutes of inactivity. The engine pings pooled connections before use and recycles them after 4 minutes, so the first query after a suspend reconnects instead of failing. A regression test covers this: `test_first_query_after_the_database_dropped_connections_succeeds`.

### Free-tier limits (verified against the providers' docs, Oct 2026)

| Service | Limit | Consequence |
|---|---|---|
| Render free web service | Spins down after 15 min without inbound traffic; ~1 min to spin up | Cold start on the first visit after idle |
| **Render free: 750 instance-hours per workspace; exceeding it suspends ALL free services in that workspace** | Render: "Render **suspends** all of your Free web services until the start of the next month" | This quota is **shared with the owner's other always-on project** in the same workspace. Render says hours are consumed "as long as it's running" and spun-down services don't consume any; *not verified:* whether the ~1 min wake-up itself counts |
| Render free | Single instance; no pre-deploy command, persistent disk, shell or one-off jobs | Migrations run in the start command; the rate limiter is in-process |
| Neon Free | 1 GB storage/project; 100 CU-hours/project/month; scale-to-zero after 5 min (can't be disabled); 6 h history | When CU-hours run out, compute is suspended until next month. An open dashboard polls every 60 s and keeps Neon awake while the tab is visible |
| Vercel Hobby | Non-commercial, personal use only | Fine for this portfolio project; commercial use needs Pro |
| Vercel proxy | Waits up to 120 s for the origin | Longer than Render's ~1 min wake-up |
| GitHub Actions (public repo) | Scheduled workflows disabled after 60 days without repo activity; schedules can be delayed or dropped under load | Backups silently stop after 60 idle days. Re-enable under *Actions* |
| GitHub artifacts | `retention-days: 14` here (allowed 1–90); downloadable by anyone with read access | Dumps are encrypted before upload |

### Environment variables

| Where | Variable | Value |
|---|---|---|
| Render | `ENVIRONMENT` | `production` (set by `render.yaml`); turns on fail-fast checks |
| Render | `DATABASE_URL` | Neon **direct** connection string (host without `-pooler`), `?sslmode=require` |
| Render | `JWT_SECRET_KEY` | Generated by Render (`generateValue: true`); never seen or pasted |
| Render | `FINNHUB_API_KEY`, `COINGECKO_DEMO_API_KEY` | Market data (the CoinGecko key is optional) |
| Render | `REGISTRATION_INVITE_CODE` | Required to register; unset means registration is disabled |
| Render **and** Vercel | `ORIGIN_SECRET` | The same random 32+ character value in both |
| Render | `ALLOWED_ORIGINS` | The Vercel production URL, e.g. `https://mystocks.vercel.app` |
| Vercel | `RENDER_API_ORIGIN` | The Render service URL, e.g. `https://mystocks-api.onrender.com` (no trailing slash) |
| GitHub secrets | `NEON_DIRECT_URL`, `BACKUP_PASSPHRASE` | For `backup.yml` only |

In production the API **refuses to start** if `DATABASE_URL`, `ORIGIN_SECRET`, `ALLOWED_ORIGINS` or `FINNHUB_API_KEY` is missing, if the JWT secret is the `.env.example` placeholder, or if `COOKIE_SECURE` is false. The error lists every problem without echoing any value.

### Deploys (CD)

- **Render** deploys from `render.yaml` with `autoDeployTrigger: checksPass`: only after the CI workflow's checks pass on the pushed commit, and only when `backend/**` or `render.yaml` changed.
- **Vercel** builds every push. *Deployment Checks* (project settings) hold the production deployment until the CI jobs `backend` and `frontend` pass.
- **The CSP hash check runs inside the Vercel build command** (`npm run build && npm run check:csp`). A build whose inline-script hash doesn't match `vercel.json` fails, so it can never be deployed, whatever CI is doing.
- **Migrations** run on every start (Render free has no pre-deploy hook). A Postgres advisory lock serialises concurrent runs. During a deploy the old instance keeps serving while the new one migrates, so **every migration must be backward-compatible with the previous release** (expand, then contract: add columns, deploy code that uses them, and only drop old columns in a later release).

### Security headers

`frontend/vercel.json` sets a strict CSP: `default-src 'self'`, `style-src 'self'`, `script-src 'self'` plus a SHA-256 hash for the one inline script (the theme pre-paint in `index.html`), `frame-ancestors 'none'`. It also sets HSTS, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` and COOP.

If you change that inline script, run `npm run build && node scripts/check-csp-hash.mjs --print` in `frontend/` and paste the printed hash into `script-src`. CI and the Vercel build fail until you do.

### Rotating `ORIGIN_SECRET`

The value must match on both sides, so rotate in this order to avoid 403s:
1. Generate a new value: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. **Vercel** → project → Settings → Environment Variables: set `ORIGIN_SECRET` (Production) to the new value. Don't redeploy yet.
3. **Render** → mystocks-api → Environment: set `ORIGIN_SECRET` to the same value and save. Render redeploys; wait until the new deploy is live.
4. **Vercel** → Deployments → latest production → **Redeploy**, so the proxy sends the new value.
5. Between steps 3 and 4 (a minute or two), `/api` requests get a 403 and the UI shows an error until the Vercel redeploy finishes. There's no dual-secret overlap window: the API accepts one value at a time.

### Backups and restore

`.github/workflows/backup.yml` runs daily (and on demand via *Run workflow*):
- `pg_dump --format=custom` from the Neon direct URL, using the `postgres:17` image;
- piped straight into `gpg --symmetric --cipher-algo AES256`, so plaintext never touches the runner's disk;
- uploaded as an artifact kept for **14 days**.

Restore:

```bash
# 1. Download the artifact (or use the Actions UI) and decrypt it.
gh run download <run-id> --name mystocks-db-<run-id>
gpg --decrypt --output mystocks.dump mystocks.dump.gpg        # prompts for BACKUP_PASSPHRASE

# 2. Restore into a throwaway Postgres 17 first and check it.
docker run -d --name restore -e POSTGRES_PASSWORD=restore -e POSTGRES_DB=restored postgres:17
docker cp mystocks.dump restore:/tmp/mystocks.dump
docker exec restore pg_restore --no-owner --no-privileges --exit-on-error -U postgres -d restored /tmp/mystocks.dump
docker exec restore psql -U postgres -d restored -c "select count(*) from users; select count(*) from transactions;"

# 3. To restore into Neon, create a new Neon branch/database and run pg_restore against its
#    direct URL, then point DATABASE_URL at it. Delete the plaintext mystocks.dump afterwards.
```

Tested: a dump made by exactly this pipeline restored into Postgres 17 with identical row counts, Alembic version and a checksum over all transactions. (On Windows Git Bash, prefix the `docker exec` commands with `MSYS_NO_PATHCONV=1`.)

### Known limitations

- **Cold start:** about 1 minute on the first visit after 15 idle minutes, by design.
- **In-memory state resets on every wake:** price caches and rate-limit counters.
- **Rate limiting is per instance:** fine on Render free (always exactly one instance); it would need a shared store such as Redis to scale out.
- **Free-tier retention:** Neon keeps 6 hours of history; backups are kept 14 days and stop if the repo is inactive for 60 days.
- **Shared Render quota:** exhausting 750 hours also suspends the owner's other free service.
- **Vercel Hobby is non-commercial.**

### First-time setup checklist

1. **Neon**: create a project in **AWS Europe Central 1 (Frankfurt)** with **Postgres 17**. Copy the **direct** connection string (Connection details with *Connection pooling* switched **off**). It must end in `?sslmode=require`.
2. **Render**: New → Blueprint → select this repo. Render reads `render.yaml`; when prompted, paste:
   - `DATABASE_URL`: the Neon direct string;
   - `FINNHUB_API_KEY`;
   - `COINGECKO_DEMO_API_KEY` (or leave empty);
   - `REGISTRATION_INVITE_CODE`: a code you choose;
   - `ORIGIN_SECRET`: a new random value from `python -c "import secrets; print(secrets.token_urlsafe(48))"`;
   - `ALLOWED_ORIGINS`: a placeholder like `https://pending.invalid` for now.

   Confirm the instance type shows **Free** and note the service URL. The first deploy waits for CI checks on the latest `main` commit.
3. **Vercel**: Add New → Project → import this repo. Set **Root Directory** to `frontend` (the framework and build command come from `vercel.json`). Under Environment Variables (Production), add:
   - `RENDER_API_ORIGIN`: the Render URL from step 2;
   - `ORIGIN_SECRET`: the same value as on Render.

   Deploy, and note the production URL.
4. **Render** → Environment: set `ALLOWED_ORIGINS` to the Vercel production URL (no trailing slash) and save; Render redeploys.
5. **Vercel** → Settings → Build and Deployment → **Deployment Checks**: add the GitHub checks `backend` and `frontend`. If that option isn't offered on Hobby, see "Vercel CD fallback" in ROADMAP.
6. **GitHub** → repo Settings → Secrets and variables → Actions → New repository secret:
   - `NEON_DIRECT_URL`: the Neon direct string;
   - `BACKUP_PASSPHRASE`: a new random value of 20+ characters, also saved in your password manager. **Without it the backups can't be decrypted.**
7. **GitHub** → Actions → *Database backup* → **Run workflow** once to confirm it succeeds.

## Status

M5 (dashboard) — auth, a transaction ledger with oversell validation, symbol search + price autofill via Finnhub/CoinGecko, average-cost P/L, and a dashboard with summary cards, an allocation donut, daily change and realized trades. See [ROADMAP.md](ROADMAP.md) for milestones and known limitations.
