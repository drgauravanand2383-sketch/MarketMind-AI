# MarketMind AI — Architecture Overview (v1.0.0)

A one-page orientation to the whole system. Every claim here is
expanded in detail elsewhere — this document exists so a new reader
doesn't have to read all 6 backend architecture docs and 9 frontend
milestone docs before understanding how the pieces fit together.

## The shape of the system

```
┌─────────────────────┐        HTTPS (REST /api/v1)        ┌──────────────────────────┐
│                      │ ───────────────────────────────▶  │                          │
│   Frontend (SPA)     │        WSS (/ws, real-time)        │   Backend (FastAPI)      │
│   React + Vite       │ ◀─────────────────────────────▶   │   Python 3.13            │
│   served as static   │                                     │                          │
│   files by nginx     │                                     └────────────┬─────────────┘
└──────────────────────┘                                                  │
                                                          ┌────────────────┼────────────────┐
                                                          ▼                ▼                 ▼
                                                    ┌───────────┐   ┌───────────┐    ┌───────────────┐
                                                    │ PostgreSQL │   │ ChromaDB  │    │ Anthropic API  │
                                                    │ (required) │   │ (optional)│    │ (optional)     │
                                                    └───────────┘   └───────────┘    └───────────────┘
```

Two independently deployable halves: a Python/FastAPI backend and a
static React/Vite frontend, talking only over the frozen `/api/v1` REST
contract and the `/ws` WebSocket protocol — never a shared database,
shared process, or any other backdoor. `Redis` is provisioned in
`docker-compose.yml` but not actually used by anything in v1.0.0 —
reserved for a future distributed rate-limiter/event-bus.

## Backend

A modular multi-agent market intelligence engine. See
`docs/architecture/BACKEND_ARCHITECTURE.md` for the full domain-package
breakdown (screening, signal detection, alerts, recommendations,
strategy evaluation, risk analytics, backtesting, explainability,
company research, portfolio intelligence, knowledge ingestion, the
morning research pipeline, the scheduler). Exposed to the outside world
through exactly two surfaces:

- **`/api/v1`** — a versioned, frozen REST API (49 paths, 55
  operations) exposing each domain engine's own service methods
  directly, with no duplicated business logic in the HTTP layer. Bearer
  JWT authentication, policy-based authorization on every non-public
  endpoint. See `docs/architecture/API_ARCHITECTURE.md`,
  `docs/architecture/AUTHENTICATION_ARCHITECTURE.md`,
  `docs/release/API_CONTRACT_V1.md`.
- **`/ws`** — a single authenticated WebSocket delivering
  already-completed backend activity in real time (alerts, backtests,
  recommendations, strategy evaluations, explainability, health-state
  changes). In-process, in-memory only — no distributed event bus, no
  message replay. See `docs/architecture/WEBSOCKET_FRAMEWORK.md`.

## Frontend

A React 19 + TanStack Router/Query single-page app, built with Vite,
served as static files (no server-side rendering, no Node.js runtime in
production — just nginx or any static host). State is split three ways:
TanStack Query owns all server-derived data (cached, invalidated by
both mutations and incoming WebSocket events), Zustand owns UI/client
state (some persisted to `localStorage`, some session-only), and the
router owns URL/navigation state. Built domain-by-domain across 9
milestones — Authentication, Dashboard, Watchlists & Portfolio,
Research & Screening, Decision Center, Historical Analysis, Real-Time
Experience, Personalization, and a Production Quality pass — each
documented in its own `docs/frontend/MILESTONE_N.md`.

## Data flow, end to end

1. A user action in the frontend calls `/api/v1/...` via a typed API
   client, or triggers a mutation that both updates the UI optimistically
   (where applicable) and invalidates the relevant TanStack Query cache
   key.
2. The backend validates, authorizes, and delegates to the owning
   domain engine — no business logic lives in the HTTP layer itself.
3. If the action produces an event the WebSocket framework knows about
   (a completed backtest, a new alert, etc.), every connected,
   subscribed client receives it in real time — the frontend's
   `useRealtimeSync` dispatch hook invalidates the matching cache keys,
   writes a Notification Center entry, and fires a toast, all from one
   incoming message.

## What ties the two halves together (and what doesn't)

- **Contract, not code sharing.** No shared types package, no
  generated client from the OpenAPI schema (in v1.0.0) — the frontend's
  own hand-written TypeScript types in `src/types/` mirror the backend's
  Pydantic schemas by convention, verified by integration tests on both
  sides, not by a build-time codegen step.
- **Two independent deployments.** The frontend never assumes anything
  about the backend's deployment topology beyond the two URLs
  (`VITE_API_BASE_URL`/`VITE_WS_BASE_URL`) baked in at its own build
  time — see `docs/release/DEPLOYMENT_GUIDE.md`.
- **API v1 is frozen.** Per `docs/release/API_VERSIONING_POLICY.md`, no
  breaking change ever lands in `/api/v1` in place — a breaking change
  means a new `/api/v2`. This is what let the 9 frontend milestones
  build against a stable target without backend coordination for each
  one.

## Where to go next

| Question | Document |
|---|---|
| How do I install/run this locally? | `docs/release/INSTALLATION_GUIDE.md` |
| How do I deploy this to production? | `docs/release/DEPLOYMENT_GUIDE.md` |
| How do I operate a running deployment? | `docs/release/ADMINISTRATOR_GUIDE.md` |
| How do I use the application? | `docs/release/USER_GUIDE.md` |
| What exactly does `/api/v1` look like? | `docs/release/API_CONTRACT_V1.md` |
| How does the backend's domain logic work? | `docs/architecture/BACKEND_ARCHITECTURE.md` |
| How does real-time delivery work? | `docs/architecture/WEBSOCKET_FRAMEWORK.md` |
| How was the frontend built, milestone by milestone? | `docs/frontend/MILESTONE_2.md` through `MILESTONE_9.md` |
| What's deliberately not done yet? | `docs/release/KNOWN_LIMITATIONS.md` |
