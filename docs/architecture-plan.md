# MyStocks — Architecture & Milestone Plan

Living reference for whoever (Claude Code included) picks up work on this repo. Read this before starting a new milestone.

## Decisions locked in

- Multi-currency: schema stores `currency` per transaction/user now; MVP hardcodes `"USD"` everywhere; real FX conversion is Phase 2 (with TASE/ILS).
- Repo: monorepo (`backend/` + `frontend/`).
- Deploy target: TBD at M7, likely Fly.io or Railway.
- Auth: argon2 password hashing, self-signup open, JWT in an httpOnly/secure/samesite=lax cookie, ~30min expiry, no refresh flow (documented MVP limitation).
- Transactions: `asset_type` is `stock | crypto`. `symbol` is free text (no exchange validation until M4's market-data provider). `executed_at` is user-supplied, not defaulted to now.
- Money/quantity: `Numeric(28,10)` in Postgres, `Decimal` end to end in Python, JSON in/out as strings (never floats) — see `backend/app/schemas/decimal.py`.
- Market data (M4): `MarketDataProvider` protocol (`backend/app/market_data/provider.py`) with Finnhub (US stocks: `/search`, `/quote`) and CoinGecko (crypto: `/search`, `/simple/price`, `/coins/{id}/history`) adapters. Each is wrapped in a two-tier in-memory cache (`cache.py`): 60s TTL for live quotes and live price-on results, no expiry (LRU-bounded) for final closes, 1h for search. Errors are never cached. Provider failures map to JSON `{detail, code}`: 404 when a symbol or price is unavailable, 503 when the provider is down or rate-limited. Search degrades per source. Prices are parsed with `parse_float=Decimal` and rounded half-even to 10 places for the API.
- **Free-tier finding (2026-09-30):** Finnhub free has **no historical prices** (`/stock/candle` is Premium; the "~1 year" belief was wrong). So stock price-on-date only resolves when the latest quote covers the date (today, or a weekend/holiday falling back to the last close; see `market_data/dates.py`). Older dates need manual entry. CoinGecko keyless history is limited to the past 365 days.
- P/L engine (M3): `backend/app/domain/pnl.py` + `cost_basis.py`. Pure functions over trades and a `price_of` lookup. Average cost sits behind a `CostBasisStrategy` protocol (FIFO later = a new class). The state is `(quantity, total_cost)`, with average = total / quantity. A buy is exact addition, a partial sell removes cost proportionally (the average is unchanged), and a sell to zero removes exactly the total, so the average resets. Buy fees are added to cost basis; sell fees are subtracted from proceeds. Replay uses `holdings.chronological()`, the same ordering as the oversell check, plus a price/fee tiebreak so results never depend on load order. Arithmetic runs in a 60-digit Decimal context (`domain/precision.py`), because the default 28 digits silently round `Numeric(28,10)` products. Rounding happens only at the API (`Money` 10dp, `Percent` 4dp, half-even). An oversold ledger (only possible after deleting a buy) raises `OversoldLedgerError`, which becomes a 409. Tests: example cases, a hand-worked example, and hypothesis properties (quantity = buys − sells; realized + unrealized = cash in − cash out + value; input-order independence; non-negative average; sells don't move the average).
- Stale prices (M3): `CachedProvider` keeps a last-known-good copy of every live quote (in memory, LRU-bounded). If a fetch fails because the provider is unavailable or rate-limited, it returns that copy with `is_stale=True` and the original `as_of`, and parks it for one 60s TTL so an outage costs one timed-out call per symbol per minute. `SymbolNotFound` is never masked. With no last-known-good copy, the holding is returned with null price fields and a `price_unavailable_reason`. Holdings fetch quotes in parallel (up to 8 threads).
- Daily change (M5): the `Quote` dataclass gained three optional fields, `reference_price`, `reference_at` and `reference_kind` (no provider method signatures changed). Finnhub: `pc`, with `reference_at` = 00:00 New York on the quote's session (`market_data/dates.us_session_start`, DST-aware). A zero or missing `pc` gives no reference, and unknown tickers (zeroed quote) are already `SymbolNotFound`. CoinGecko: `include_24hr_change`, base = `price / (1 + pct/100)` (`price_before_change`), `reference_at` = `as_of − 24h`, and a null % gives no reference. The cache and stale fallback carry the fields unchanged, so a stale quote keeps its own consistent c/pc pair. The pure `domain/daily_change.py` computes `qty_now·P − qty_at_ref·R − bought_since + sold_since` (buys since the reference use the buy price), and missing data gives `None`, never 0. The API exposes `day_change*` per holding and `total_day_change*` + `day_change_bases` (so a mixed stock+crypto total is labelled) on the summary. The total covers open holdings only.
- Dashboard UI (M5): plain-SVG donut (no chart dependency). At most 5 slices + "Other", in alphabetical ring order, with a categorical palette checked by the dataviz validator for ring-adjacent pairs in light (#fff) and dark (#121212). Prices poll every 60s (= cache TTL), paused when the tab is hidden (TanStack `refetchIntervalInBackground: false`, checked in the v5.104 source). Strings live in `frontend/src/strings.ts` with a pinned date locale, CSS uses logical properties for RTL, and there's temporary hash navigation (router in M6).
- Frontend design system (M5.6): all colours are CSS custom properties on `:root`, with a dark set under `:root[data-theme='dark']`. Components reference tokens only (audited: no colour literals outside the two token blocks). Text/background pairs are WCAG-checked at ≥4.5:1 in both themes, and the dark primary button pair (white on `#6a5ff5`, 4.60:1) must be recomputed before it changes. The theme is light/dark/system: `src/theme.ts` + `useTheme`, saved in `localStorage` inside try/catch, and applied before first paint by an inline script in `index.html` (needs a CSP hash or nonce at deploy). The layout is mobile first: a bottom tab bar below 768px, holdings as cards below 1024px, other tables scroll inside their card with a sticky symbol column, and touch targets are ≥44px. Data text is ≥14px with tabular numerals; 12px is only for secondary labels. `prefers-reduced-motion` turns off transitions and shimmer. All copy lives in `src/strings.ts`, with no new dependencies (system font stack, inline SVG icons).
- Production (M5.5): Vercel (static SPA + CSP + `/api` reverse proxy) → Render free (Docker; `start.sh` runs `alembic upgrade head` then uvicorn, since free has no pre-deploy hook) → Neon (direct connection, `sslmode=require`).
  - **Single origin:** the browser only talks to Vercel, so the cookie stays first-party.
  - **Origin lock:** Vercel adds `x-origin-secret` (from its env) to proxied requests; the API returns a generic 403 to `/api` without it, compared constant-time, and only then trusts `X-Forwarded-For` for client IP.
  - **CSRF:** `ALLOWED_ORIGINS` checks `Origin` on state-changing requests.
  - **Caching:** `Cache-Control: no-store` on all `/api`.
  - **Signup:** an invite code (`REGISTRATION_INVITE_CODE`, constant-time; unset in production means disabled).
  - **Rate limits:** in-process sliding windows (valid because free means a single instance).
  - **Fail-fast:** the production config fails at startup without echoing values (`hide_input_in_errors`).
  - **Engine:** `pool_pre_ping`, `pool_recycle=240`, pool 3+2, because Neon suspends after 5 min.
  - **Migrations:** serialized by a Postgres advisory lock.
  - **Probes:** `/healthz` (no DB) for Render's health check, `/readyz` (DB).
  - **No keep-alive pinger:** the workspace's free hours are shared.
  - **Cold-start UX:** queries retry 502/503/504 and network errors every 5 s for about 2 min, and a "server is waking up" notice appears after 8 s.
  - **CSP:** strict, with a SHA-256 for the inline theme script; drift is checked inside the Vercel build command and in CI.
  - **Backups:** daily `pg_dump` → gpg AES256 → 14-day artifact; restore tested.
  - **CD:** Render `checksPass`; Vercel Deployment Checks (CLI fallback documented).
- Personality layer (M5.7):
  - **Tokens:** redesigned in both themes. The light theme is warm violet→peach→sunny; dark is its own violet-night set, not an inversion. Every text pair is ≥4.5:1, and the light gain colour was darkened to `#087538` to clear the warmer gradient. The donut palette was re-validated on the new dark card `#1a1730` and is unchanged.
  - **Colour rules:** accent hues are only for chips, tags and illustrations. Green means gain; red means loss or danger (Delete and errors use a separate `--danger` token, following Norman/Shneiderman conventions); neither is decorative.
  - **Destructive actions:** deleting a transaction goes through a two-step native `<dialog>` confirmation. Focus starts on the safe button, the step that deletes uses solid `--danger-strong`, and a buy with later sells gets a warning. The Delete label is visible at every width.
  - **Font:** Rubik variable, self-hosted (Latin and Hebrew faces, OFL).
  - **Mascot:** Ledgie, an original inline-SVG notebook. It is `aria-hidden` and coloured via CSS classes, never inline styles, so the CSP stays strict.
  - **Motion:** a big.js count-up once per load; a single SVG mask for the donut draw-in; a CSS-only springy theme thumb (data attribute, RTL-mirrored); playful shimmer. All of it is reduced-motion safe.
  - **Celebration:** a one-time first-entry celebration (0→1 in the session plus a `localStorage` flag), never tied to P/L.
- Oversell validation: replays a symbol's trade history in `executed_at` order (buys before sells at the same timestamp), not just a final-totals comparison — catches backdated sells. See `backend/app/domain/holdings.py`. Writes are serialized per-user via `SELECT ... FOR UPDATE` on the user row.

## Repo structure

```
MyStocks/
├── backend/app/{api,core,db,domain,market_data,schemas}/
├── backend/tests/{unit,integration,live}/   (live = real-network, excluded by default)
├── frontend/src/{api,components,pages,hooks}/
├── docker-compose.yml, .env.example, render.yaml
├── frontend/vercel.json        (proxy, CSP, security headers)
├── .github/workflows/          (ci.yml gates deploys; backup.yml encrypted pg_dump)
├── docs/architecture-plan.md   (this file)
└── ROADMAP.md                  (phase 2/3/4 hooks + known MVP gaps)
```

## Milestone status

| # | Milestone | Status |
|---|---|---|
| M0 | Skeleton (FastAPI + React scaffold, docker-compose, CI) | Done, committed |
| M1 | Auth (register/login/JWT cookie) | Done, verified live |
| M2 | Transactions CRUD + oversell validation | Done, verified live |
| M3 | P/L engine (avg cost basis, unrealized/realized P/L) | Done, verified live |
| M4 | Market data provider (Finnhub + CoinGecko, TTL cache) | Done (pulled ahead of M3) |
| M5 | Portfolio dashboard | Done, verified live in browser |
| M5.6 | Visual redesign (tokens, theming, mobile-first, a11y) | Done, verified in browser |
| M5.5 | Free-tier production deploy (Vercel + Render + Neon) | Built and tested locally; live verification pending |
| M5.7 | Personality pass (mascot, warm tokens, Rubik, motion, first-entry celebration) | Done, verified in browser |
| M6 | Price chart (+ replace hash navigation with a router) | Next |
| M7 | Polish + deploy | Not started |

## The 3 riskiest technical decisions (from initial planning)

1. **Market data providers** — Finnhub (official free-tier API key) + CoinGecko, both behind a `MarketDataProvider` interface so swapping providers later is a one-adapter change. Switched away from yfinance's unofficial scraping to keep only permitted data sources.
2. **Cost-basis correctness** — the module most worth heavy testing (property-based tests earn their cost here). M2's `domain/holdings.py` already sets the pattern: pure functions, no DB/FastAPI imports, tested in isolation.
3. **JWT strategy** — short-lived cookie, no refresh flow in MVP; documented limitation, not silently skipped.

## Known MVP gaps (see ROADMAP.md for the full list)

Deleting a transaction doesn't retroactively re-validate the rest of that symbol's history; USD only; symbols suggested by search but not validated on save; no transaction edit UI yet (PATCH exists, tested, no frontend for it); no historical stock prices on Finnhub's free tier; crypto history limited to 365 days; transactions store the crypto ticker, not the CoinGecko id.
