# Roadmap

| Milestone | Scope | Status |
| --- | --- | --- |
| M0 | Skeleton: FastAPI + React scaffold, docker-compose, CI | Done |
| M1 | Auth: register / login / me, argon2 + JWT cookie | Done |
| M2 | Transactions ledger: CRUD, oversell validation, transactions page | Done |
| M3 | Average-cost P/L engine on top of `domain/holdings.py` | Next |

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
- **Symbols are free text.** They're uppercased, but not validated against any exchange
  until market data lands in M4.
- **Oversell ordering is by `executed_at`, with buys before sells at an identical timestamp.**
  Real intraday order beyond timestamp precision isn't modelled.
- **The client-side oversell hint only compares final totals.** The server's
  chronological check is authoritative.
- **No edit UI yet.** `PATCH /api/transactions/{id}` exists and is tested, but the page
  only supports add and delete.
