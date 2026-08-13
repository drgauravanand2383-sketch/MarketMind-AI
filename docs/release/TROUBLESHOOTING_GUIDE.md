# MarketMind AI — Troubleshooting Guide (v1.0.0)

Common problems and how to diagnose them.

## Frontend shows a blank page with a console error mentioning "Missing required environment variable"

The build was made without `VITE_API_BASE_URL`/`VITE_WS_BASE_URL` set
(production builds only — dev mode falls back to localhost). These are
**build-time** values (`docs/release/PRODUCTION_CONFIGURATION_GUIDE.md`'s
Frontend section) — setting them on the running container has no
effect. Rebuild with `--build-arg VITE_API_BASE_URL=... --build-arg
VITE_WS_BASE_URL=...` (Docker) or as environment variables before
`npm run build`.

## Frontend loads but every API call fails / CORS errors in the console

`VITE_API_BASE_URL` points at the wrong backend, or the backend's
`ALLOWED_ORIGINS` doesn't include the frontend's actual origin. Check
`ALLOWED_ORIGINS` in the backend's `.env` — it must list the frontend's
real origin (scheme + host + port), not `localhost` if the frontend
isn't actually served from localhost.

## WebSocket won't connect / notification bell never updates

1. Confirm `VITE_WS_BASE_URL` is correct and uses `ws://`/`wss://` (not
   `http://`/`https://`).
2. If behind a reverse proxy, confirm it's configured to pass through
   the `Upgrade: websocket` header — a plain HTTP-only proxy config
   rejects the handshake (`docs/release/DEPLOYMENT_GUIDE.md` §7).
3. Check the connectivity banner at the top of the page (visible from
   any page) — it distinguishes "offline" from "real-time connection
   unavailable" from "degraded."
4. The frontend reconnects automatically with exponential backoff; a
   manual "Reconnect" button appears on the dashboard's Connectivity
   card once the automatic attempts are exhausted.

## `alembic upgrade head` fails

- Confirm `DATABASE_URL` (or the individual `POSTGRES_*` fields) points
  at a reachable, empty-or-already-migrated database.
- `alembic current` shows what revision the database thinks it's at —
  compare against the latest revision in `backend/alembic/versions/`.
- Never hand-edit an already-shipped migration
  (`docs/release/UPGRADE_POLICY.md`) — if a migration is broken, add a
  new one that fixes it forward.

## Backend starts but `/api/v1/health` shows a repository/service as `UNHEALTHY`

Expected and non-fatal for optional dependencies (ChromaDB, Anthropic) —
company research/portfolio intelligence/knowledge-hub features degrade
to `503` for just those endpoints; everything else keeps working. Check
`/api/v1/ready`'s `data.blocking_issues` to see whether anything
*required* (Postgres) is actually down.

## `docker build` fails on the backend with a "Readme path must be within the project directory" error

This was a real bug in `backend/pyproject.toml`, fixed in v1.0.0 (its
`readme` field now points at `backend/README.md`, not `../README.md`).
If you see this on a checkout predating the fix, pull the latest
`backend/pyproject.toml` and `backend/README.md`.

## `pip install -e .` / `uv sync` fails with a Python version error

The backend requires Python 3.13+ (`backend/pyproject.toml`'s
`requires-python`). Check your active Python version; install 3.13+ if
needed (`uv python install 3.13` if using uv).

## Tests are flaky / a test fails once but passes on rerun

The frontend's test suite has shown transient worker-pool startup
timeouts and occasional test timeouts under heavy parallel load in this
project's own CI/dev history — always rerun a failing test in isolation
(`npx vitest run <path>`) before treating it as a real regression. A
failure that doesn't reproduce in isolation is environmental, not a
code problem.

## A user reports a broken page but the backend logs show nothing relevant

Frontend errors are caught by React error boundaries and logged only to
the *browser's* console (`[ErrorBoundary] ...`) — there is no
server-side aggregation of frontend errors in v1.0.0
(`docs/release/OBSERVABILITY_VERIFICATION.md`). Ask the reporting user
to open their browser's DevTools console and share what's there.

## Session ends unexpectedly / user is logged out mid-task

Expected if the access token's refresh attempt fails (revoked/expired
refresh token, or `SECRET_KEY` was rotated — every existing token
becomes invalid). The user is redirected to `/unauthorized`
immediately, not silently — if this is happening more than expected,
check `ACCESS_TOKEN_EXPIRE_MINUTES`/`AUTH_REFRESH_TOKEN_EXPIRE_MINUTES`
aren't set unexpectedly short.
