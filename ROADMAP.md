# Roadmap

| Milestone | Scope | Status |
| --- | --- | --- |
| M0 | Skeleton: FastAPI + React scaffold, docker-compose, CI | Done |
| M1 | Auth: register / login / me, argon2 + JWT cookie | Done |
| M2 | Transactions ledger: CRUD, oversell validation, transactions page | Done |
| M4 | Market data: Finnhub + CoinGecko search, quotes, price-on-date autofill (pulled ahead of M3) | Done |
| M3 | P/L engine (average cost) + holdings/summary/realized endpoints, stale-price fallback | Done |
| M5 | Portfolio dashboard: summary cards, allocation donut, daily change, realized trades | Done |
| M6 | Price charts (TradingView Lightweight Charts) + a real router | Next |

## Known MVP limitations

### Auth (M1)

- **No refresh tokens.** The access token is a 30-minute JWT in an httpOnly cookie. When it
  expires, the user is simply logged out and must log in again, even mid-session. A
  refresh-token flow (long-lived, rotating, server-revocable) is deferred.
- **No server-side revocation.** A JWT stays valid until it expires; there is no logout
  endpoint or token blocklist yet. Deleting the user does invalidate their token, because
  `get_current_user` reloads the user on every request.
- **No rate limiting** on `/api/auth/login` or `/api/auth/register`.
- **No email verification or password reset.**
- **CSRF** relies on `SameSite=Lax` plus JSON-only request bodies. That's sufficient while
  the frontend and API share an origin, but it needs revisiting (CSRF token or
  `SameSite=Strict`) if they are ever split across sites.

### Transactions (M2)

- **Deleting a transaction is not re-validated.** Create and edit both check that no sell
  exceeds what was held at that point in the history, but `DELETE` does not. Deleting a buy
  can therefore leave a later sell uncovered (a negative running balance). A fix would run
  the same `find_oversell` check on delete and either reject it or flag the ledger as
  inconsistent; deferred for M2.
- **USD only.** `currency` is stored per transaction, but the API accepts only `"USD"`.
  Multi-currency (ILS / TASE) is Phase 2.
- **Symbols aren't validated on save.** The form now suggests real symbols (M4), but
  `POST /api/transactions` still accepts any non-empty symbol, so a hand-typed typo is stored.
- **Oversell ordering is by `executed_at`, with buys before sells at an identical timestamp.**
  Real intraday order beyond timestamp precision isn't modelled.
- **The client-side oversell hint only compares final totals.** The server's
  chronological check is authoritative.
- **No edit UI yet.** `PATCH /api/transactions/{id}` exists and is tested, but the page
  only supports add and delete.

### Market data (M4)

Verified against Finnhub's own API spec (embedded in finnhub.io/docs/api) and live
CoinGecko responses on 2026-09-30.

- **No historical stock prices on free plans.** Finnhub's `/stock/candle` is marked
  "Premium Access Required", with no free lookback window. Free is limited to `/search` and
  `/quote`, which returns the latest price only. So a stock's price-on-date autofills only
  when the latest session answers it: today, or a weekend/holiday that falls back to the last
  close. Any older date returns `price_unavailable` and the form asks for manual entry. Fixing
  this means a paid Finnhub plan, or a second adapter just for history. Tiingo's free tier has
  30+ years of EOD data but is licensed "internal use only", which conflicts with open signup.
- **Crypto history is limited to the past 365 days** on CoinGecko's free/keyless API.
  Older dates return `price_unavailable`, so the price is entered manually.
- **Crypto "close" is CoinGecko's 00:00 UTC snapshot of the following day**, not an
  exchange-specific close.
- **Crypto tickers aren't unique.** A transaction stores the ticker (e.g. `BTC`), not the
  CoinGecko coin id. The form passes the picked coin's id for autofill. A lookup by ticker
  alone takes the highest-ranked exact match, which could price the wrong coin for obscure
  tickers. M5's dashboard will need either a stored `provider_id` column or the same heuristic.
- **Finnhub search is limited to US listings** (`exchange=US`), because free `/quote` only
  covers US stocks.
- **Caches are in-memory and per-process.** They're lost on restart and not shared if the
  backend is ever scaled out.
- **Last-known-good quotes are in memory only.** After a backend restart, a symbol has no
  fallback until it has been fetched successfully once.
- **Rate limits.** The free Finnhub tier allows 60 calls/min, and keyless CoinGecko allows
  much less. Search is debounced (300ms) and cached for 1 hour. A rate-limited provider
  degrades to a message, never to stale data.

### P/L (M3)

- **Average cost only.** FIFO and specific-lot identification aren't built yet. The
  `CostBasisStrategy` interface in `domain/cost_basis.py` is where they'd plug in.
- **Positions are grouped by symbol alone, like the ledger.** A stock and a coin sharing a
  ticker would be merged into one position. The latest trade's `asset_type` decides which
  provider prices it.
- **An oversold history returns 409.** This only happens after deleting a buy (see M2), and
  then every portfolio endpoint refuses rather than showing wrong numbers. The message names
  the symbol to fix.
- **Partial portfolio pricing.** Summary totals for market value and unrealized P/L cover
  priced holdings only. `unpriced_symbols` lists the rest, and cost basis and realized P/L
  always cover everything.
- **No tax-lot, wash-sale or holding-period handling.**

### Dashboard (M5)

- **Hash navigation is temporary.** The Dashboard and Transactions views switch on
  `#/` vs `#/transactions` (`hooks/useHashRoute.ts`). **M6 should introduce a real router**
  (e.g. React Router or TanStack Router) once there are per-symbol chart pages.
- **Daily change, stocks:** "since previous close" means the close before the session of the
  latest quote. Pre-market, that's the last *completed* session's change, possibly days old.
  `day_change_reference_at` (00:00 New York on that session) is shown so this is visible.
  A trade counts as "today's" if it's on or after that midnight. After-hours trades from the
  previous evening count as before the reference, which is a simplification.
- **Daily change, crypto:** rolling 24h, with the base price derived from CoinGecko's
  percentage (`price / (1 + pct/100)`). That's exact given the percentage, but the percentage
  itself is CoinGecko's. Not comparable to the stock basis, and the UI labels both.
- **The day-change total covers open positions only.** A position fully closed since the
  reference isn't included (it would need a quote for a symbol no longer held).
- **Fees are excluded from daily change**; they're in cost basis and realized P/L.
- **Polling cost:** each open stock symbol costs at most one Finnhub call a minute, shared
  across users of one backend process, so the free tier's 60/min fits about 50 distinct stock
  symbols. CoinGecko is called per coin; batching IDs into one `/simple/price` call is a cheap
  future improvement.
- **The donut shows at most 5 named slices + "Other",** ordered alphabetically, so its
  colors stay next to the neighbours they were validated against. A symbol's color can
  change when the set of named holdings changes.
- **UI strings** for the new and touched components live in `frontend/src/strings.ts`
  (dates follow its `locale`). The older login and transaction-form copy hasn't been moved
  there yet. No Hebrew yet.
