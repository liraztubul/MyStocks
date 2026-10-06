# Roadmap

| Milestone | Scope | Status |
| --- | --- | --- |
| M0 | Skeleton: FastAPI + React scaffold, docker-compose, CI | Done |
| M1 | Auth: register / login / me, argon2 + JWT cookie | Done |
| M2 | Transactions ledger: CRUD, oversell validation, transactions page | Done |
| M4 | Market data: Finnhub + CoinGecko search, quotes, price-on-date autofill (pulled ahead of M3) | Done |
| M3 | P/L engine (average cost) + holdings/summary/realized endpoints, stale-price fallback | Done |
| M5 | Portfolio dashboard: summary cards, allocation donut, daily change, realized trades | Done |
| M5.6 | Visual redesign: design tokens, light/dark/system theme, mobile-first layout, skeletons, empty state | Done |
| M5.5 | Free-tier production deploy: Vercel + Render + Neon, invite-only signup, rate limits, CSP, encrypted backups | Built; live verification pending |
| M5.7 | Personality pass: Ledgie mascot, warm tokens in both themes, Rubik font, motion, first-entry celebration | Done |
| M5.8 | Sell from holdings (dialog with 25% / 50% / All), buy-only add form, status-aware write errors | Done |
| M5.9 | Theme toggle reduced to light/dark; OS preference until the user picks | Done |
| M6a.1 | Real router (React Router), deep links, legacy `#/` redirect | Done |
| M6a.g | Stock-data allowlist: one server-side gate for all stock market data | Done |
| M6 | Price charts (TradingView Lightweight Charts) | In progress (M6a) |

## Watchlist (planned, not started)

A watched symbol is an asset you don't necessarily hold, so the per-asset page is
`/assets/:symbol` and the M6a history endpoint already works without a position (see "Price
history (M6a)" below). **All stock data stays behind `STOCK_DATA_ALLOWED_EMAILS`** in every
phase: a blocked user can watch stocks, but sees them without prices, like a blocked holding.

- **W1: the list.** Add and remove symbols; each row shows the price, daily change and a link to
  the asset page. Needs a `watchlist_items` table (user, asset type, symbol, provider id) and
  reuses the quote path and its cache, so a row costs what a holding costs.
- **W2: a sparkline per row**, drawn from the `daily_closes` cache. **Design the request budget
  first:** a list of N symbols can mean N history backfills on first view, and Tiingo's free
  tier allows 50 requests/hour, 1,000/day and 500 symbols/month. Likely answers: serve only
  what's cached, backfill lazily per visible row, and bring back the per-provider budget that
  M6a dropped (see "Price history (M6a)").
- **W3: reports**, starting with SEC EDGAR filings (public, keyless, with a published fair-access
  policy to follow) and an earnings calendar (provider to be chosen and its terms checked).
- **Phase 2: news with Hebrew summaries**, only after provider licensing is checked: Finnhub's
  plans are personal use only, and summaries would be derived results, which its terms also
  restrict.
- **Phase 3: price alerts.** These need a background worker and a hosting decision first: the
  free Render instance sleeps when idle, so alerts checked in-process would silently miss
  events. Options to weigh then: a paid always-on instance, a scheduled job (GitHub Actions or
  Render cron), or a hosted queue.

## Price history (M6a, in progress)

- **The history endpoint doesn't require a position.** Any symbol gets a normal chart. Markers
  come only from the requesting user's own ledger, and are `[]` when there are no trades. 404
  means an unknown symbol only.
- **Stock history follows the allowlist:** a blocked user gets 200 with `available: false`
  (the view convention in `app/market_data/access.py`), whether or not the symbol exists.
- **No request budget in M6a.** A 429 or any other provider failure is treated as a provider
  failure: serve the cache marked stale, plus a short in-memory cooldown. Idempotent upserts
  make duplicate fetches harmless. **Bring the budget back** (a calls table counting
  requests per hour, day and month) before anything fans out across many symbols at once
  (W2 sparklines, M6b portfolio-over-time) or when there is more than one backend instance.

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
  inconsistent; deferred for M2. Since M5.7 the UI mitigates it: deleting a buy with later
  sells of the same symbol shows an explicit warning in the confirmation dialog. The server
  still doesn't block it. **More visible since M5.8:** a sell can no longer be entered for
  something you don't hold, so the add form feels "safe". A delete is now the only way left to
  make the ledger inconsistent, and the next portfolio read then fails until it's fixed.
- **USD only.** `currency` is stored per transaction, but the API accepts only `"USD"`.
  Multi-currency (ILS / TASE) is Phase 2.
- **Symbols aren't validated on save.** The form now suggests real symbols (M4), but
  `POST /api/transactions` still accepts any non-empty symbol, so a hand-typed typo is stored.
- **Oversell ordering is by `executed_at`, with buys before sells at an identical timestamp.**
  Real intraday order beyond timestamp precision isn't modelled.
- **The sell dialog's "more than you hold" check compares against today's holding only.** A
  backdated sell can pass it and still be refused by the server's chronological check; the
  dialog then shows the server's message and keeps the input. The server is authoritative.
- **No edit UI yet.** `PATCH /api/transactions/{id}` exists and is tested, but the page
  only supports add and delete.

### Stock-data allowlist (M6a)

- **Why:** Finnhub ("strictly for personal use") and Tiingo (free: "internal use") don't allow
  showing their data to other people. `STOCK_DATA_ALLOWED_EMAILS` decides who sees stock market
  data at all: quotes, price-on-date, search and (Stage 4) history.
- **Rule:** listed emails only. Unset or empty means everyone in development and nobody in
  production, decided by `ENVIRONMENT` (the same mechanism as `REGISTRATION_INVITE_CODE`;
  `render.yaml` sets `ENVIRONMENT=production`).
- **One place, default-deny:** routers can only get market data through
  `app.market_data.access.UserMarketDataDep`. The ungated `shared_market_data` is checked by a
  structural test (no router imports it, and in FastAPI's dependency graph it only appears under
  the gate). The gate sits in front of the providers' caches, so a blocked user can't receive a
  quote cached for an allowed one, stale copies included.
- **Error convention** (documented in `app/market_data/access.py`): actions (quote, price-on)
  answer 403 `{code: "not_available_on_deployment"}`; views (holdings, summary, history) answer
  200 with prices null plus the code or `available: false`. The frontend maps the code to a
  specific message in `api/writeErrors.ts`.
- **Assumption, shown in the UI:** blocked stock positions keep their cost basis, which counts
  in "Cost basis (all)". Value and unrealized P/L cover priced holdings only, measured against
  `priced_cost_basis`; subtracting value from the full cost basis is not a P/L. Realized P/L is
  unaffected (it uses your own trade prices). Typing a price yourself always works.
- **Emails are unverified.** Registration normalizes emails (trimmed, lowercase), and a database
  CHECK keeps every stored email lowercase, so the unique index is effectively case-insensitive
  and a differently-cased copy of an allowlisted address can't register. But anyone with the
  invite code could register an allowlisted address nobody has claimed yet, so **only list
  addresses that are already registered.** Email verification would close this.

### Selling (M5.8)

- **Buys are added on the Transactions page; sells start from a holding.** The add form has no
  Side selector and always posts `side: "buy"`. The API still accepts both, so the server-side
  oversell check is unchanged and remains the source of truth.
- **The quick amounts round down.** 25% and 50% are computed with big.js and rounded down to 10
  decimal places (the API's precision), so they never exceed what's held. When that rounds to 0
  (a dust position), the button is disabled, with a visible explanation rather than a tooltip.
  "All" sends the exact quantity string the API returned.
- **Price defaults only when it's fresh.** If the market price is stale or unavailable, the
  field starts empty and is required, and a hint says why.
- **Write errors are handled by status.** 400/422 show the server's text and keep the dialog
  open; 401 drops cached data and returns to the login page with a "session timed out" notice;
  403 shows a generic "not allowed"; 429 uses `Retry-After`; anything else is a generic retry
  message. This applies to the add form and the delete dialog too.
- **Errors carry an icon and words, never colour alone** (`FormError`); field errors are tied
  to their inputs with `aria-describedby` and `aria-invalid`.
- **The modal is shared** (`Modal`): native `<dialog>`, focus returns to the opener, or a
  fallback when the opener is gone (selling the last unit removes its Sell button). It becomes
  a bottom sheet below 600px.
- **The holdings table now starts at 1200px** (cards below), so the Sell button is never pushed
  past a horizontal scroll edge.
- **No realized-P/L preview in the dialog.** Computing it client-side would duplicate the
  engine. A possible later milestone: `POST /api/portfolio/preview-sell` that runs the same
  engine on a hypothetical sell and returns the realized P/L, without saving anything.

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
- **Risk: CoinGecko's Demo plan is described as "for testing and exploration"** on its pricing
  page (checked 2026-10-06; 100 calls/min, 10,000 calls/month). It also requires the
  attribution "Data provided by CoinGecko" with a link to https://www.coingecko.com/en/api,
  which the app footer shows. If the plan's terms tighten, the provider sits behind the
  `MarketDataProvider` interface, so swapping it is a one-adapter change.
- **Finnhub's plans are "strictly for personal use"**, with no sharing of data "with anyone or
  any 3rd party without written approval" (terms checked 2026-10-06). Finnhub doesn't require
  attribution. Showing stock data to other users is being gated behind an allowlist (M6a).

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

- **Routing (since M6a):** React Router 7 with real paths (`/`, `/transactions`,
  `/assets/:symbol`). Old `#/…` links are rewritten to paths on load and on hash change, and
  `/holdings/:symbol` (the first name of the asset page) redirects to `/assets/:symbol`.
- **Build files live under `/static/`** (Vite `build.assetsDir`), not Vite's default `/assets/`,
  so they can't collide with the `/assets/:symbol` route. The SPA fallback (Vercel rewrite,
  nginx) excludes `/api/`, `/static/` and `/fonts/`, so a missing bundle or font is a real 404.
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

### Frontend / design (M5.6)

- **CSP for the pre-paint theme script.** `index.html` has a small classic inline `<script>`
  that applies the saved theme before first paint, to avoid a flash of the wrong theme. A
  production Content-Security-Policy without `'unsafe-inline'` will need a **hash** (it's static,
  so `'sha256-…'` of its exact text works) or a per-response **nonce** for it. That's part of the
  M7 deploy work. Verified: Vite leaves the script byte-identical in `dist/index.html` (676 bytes)
  and places it before the module bundle.
- **The theme logic is duplicated** between that inline script and `src/theme.ts` (storage key,
  the dark-mode test, the `theme-color` values), because the script must run before any module
  loads. Both carry a "keep in sync" comment.
- **Theme toggle is light/dark only (since M5.9).** The rule (in both places): a stored `'light'`
  or `'dark'` wins; anything else (nothing stored, the retired `'system'` value, or junk) means
  "no choice yet" and follows `prefers-color-scheme`, including live OS changes. Old `'system'`
  values are not rewritten; they're ignored until the user clicks a segment. There is no way
  back to "follow the OS" once a choice is made, short of clearing site data.
- **No frontend test runner.** Lint, typecheck, build and the throwaway Playwright checks in
  the scratchpad are the only frontend gates. Adding Vitest + Testing Library (plus a Playwright
  smoke test in CI) is the natural next step.
- **Native date-time picker:** the transaction form's `datetime-local` input renders in the
  browser/OS locale (e.g. `dd/mm/yyyy`), not `strings.ts`'s `locale`. Browsers don't let pages
  control that.
- **Holdings switch from cards to a table at 1024px,** not the 768px first proposed. At tablet
  width the table pushed the P/L columns behind a sideways scroll. The other tables scroll
  inside their card with a sticky symbol column at every width.
- **RTL readiness:** layout uses logical properties throughout, but no page has been rendered
  with `dir="rtl"` yet.
- **Follow-up: `npm audit` reports one high-severity advisory** in `source-map-js`
  (GHSA-68fv-2mgg-jv7q, denial of service through crafted source maps). It's a build-time
  dependency of the Vite toolchain and isn't shipped to the browser. Left alone on purpose
  (2026-10-06); revisit with the next Vite update or `npm audit fix` in its own commit.

### Deployment (M5.5)

- **Vercel CD fallback.** If Deployment Checks aren't available on the Hobby plan (the docs
  don't say which plans have them), disable Git-triggered production deploys
  (`"git": {"deploymentEnabled": {"main": false}}` in `vercel.json`) and add a CI job that
  runs `npx vercel deploy --prod` after `backend` and `frontend` pass. That needs GitHub
  secrets `VERCEL_TOKEN`, `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID`.
- **Origin-secret rotation has a short 403 window.** The API accepts exactly one
  `ORIGIN_SECRET`. Accepting a comma-separated old+new pair during rotation would make it
  seamless.
- **Rate limits are in-process** and reset on every spin-down; scaling out would need a shared
  store such as Redis. Limits: login 10/IP/5 min plus 5 failures per (IP, email)/15 min;
  register 5/IP/hour.
- **No keep-alive by design.** The Render workspace's 750 free instance-hours are shared with
  another always-on service, so MyStocks sleeps when idle and every first visit after
  15 minutes cold-starts (~1 min).
- **To confirm on first deploy** (not stated in the docs I could read):
  - Docker runs on Render's *free* instance type (fallback: `runtime: python` with build and
    start commands);
  - Vercel passes `Set-Cookie` through `routes` with an external `dest`, and keeps the query
    string (needed by `?symbol=`, `?q=`, `?date=`);
  - the shape of `X-Forwarded-For` as Render receives it;
  - Neon's Postgres major version matching the `postgres:17` dump client;
  - whether Render counts spin-up time toward instance hours.
- **Migrations must stay backward-compatible** (expand then contract), because the old
  instance serves while the new one migrates.

### Personality (M5.7)

- **Font: Rubik (variable 300–900, SIL OFL 1.1),** self-hosted in `frontend/public/fonts/`.
  It's split into a Latin face (35 KB, preloaded) and a Hebrew face (9 KB), and the Hebrew file
  downloads only when Hebrew characters appear (`unicode-range`); verified in a browser.
  Rubik's default digits are proportional, so every number relies on `tabular-nums`, which
  switches to its `.tf` digits (all 600 units wide).
- **Colour semantics follow usability conventions (Norman, Shneiderman).** Green means gain.
  Red means loss **or danger**: destructive actions (Delete) and error messages use a separate
  `--danger` token, with the same red, so users recognise them instantly. Red is never
  decorative. Accent hues (violet, coral, cyan, sunny) decorate chips, tags and illustrations
  only, never numbers.
- **Delete takes two deliberate confirmations (error prevention; the action can't be undone).**
  A native `<dialog>` opens (with focus trap, Esc to cancel and an inert background built in).
  Step 1 names the exact transaction; step 2 states the consequence, plus a warning when a buy
  has later sells, and only then shows the solid red "Yes, delete permanently". In both steps
  focus starts on the safe button, so a stray Enter cancels. Afterwards focus returns to the
  opener, or to the table if its row is gone. The row's "Delete" button keeps its text label at
  every width; below 1024px the date wraps instead. There's no undo, so the confirmation stands in for it.
- **Count-up** runs once per page load, on the hero value only. Its frames are computed with
  big.js, and it settles on the API's exact string; screen readers get only the final value.
- **First-entry celebration** is once per browser (`localStorage`), not per account: a second
  account on the same browser won't see it.
- **Animations are CSS-only** (draw-in mask, sparkles, springs) and collapse to their final
  state under `prefers-reduced-motion`.
- **Not done yet:** a Hebrew UI. The font supports it; the strings table and RTL rendering
  still need work (see M5.6).
- **Theme colours appear in three places:** `index.css` (`--bg`), `src/theme.ts` and the
  pre-paint script in `index.html`. Changing them changes the script's CSP hash, which the
  build check (`npm run check:csp`) catches.
