# MarketMind AI — Installation Guide (v1.0.0)

Getting a full local development environment running — both halves of
the app, talking to each other. For running this in production instead,
see `docs/release/DEPLOYMENT_GUIDE.md`.

## Prerequisites

- Python 3.13+ and [uv](https://docs.astral.sh/uv/) (backend)
- Node.js 22+ and npm (frontend)
- Docker and Docker Compose (for Postgres/Redis/ChromaDB — or run them
  yourself directly if you prefer)
- An Anthropic API key, if you need company research / portfolio
  intelligence (everything else works without one)

## 1. Clone and configure

```bash
git clone <this repository>
cd MarketMind-AI
cp .env.example .env
# edit .env — see docs/release/PRODUCTION_CONFIGURATION_GUIDE.md for
# every field; the development defaults work as-is for local use
```

## 2. Start infrastructure

```bash
docker compose up -d
```

Starts Postgres, Redis, and ChromaDB only (see `docker-compose.yml`) —
the backend and frontend run natively in the next two steps, for a
fast dev inner loop (hot reload on both sides). This is deliberately
**not** the same as `docker-compose.prod.yml`, which containerizes the
backend and frontend too — see `docs/release/DEPLOYMENT_GUIDE.md` if
that's what you actually want.

## 3. Backend

```bash
cd backend
uv sync
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify: `curl http://localhost:8000/api/v1/health` and
`curl http://localhost:8000/api/v1/ready` should both return `200`.
`http://localhost:8000/docs` is the interactive Swagger UI.

## 4. Frontend

In a second terminal:

```bash
cd frontend
cp .env.example .env   # defaults already point at localhost:8000 — no edits needed for local dev
npm install
npm run dev
```

Verify: `http://localhost:5173` loads the app and redirects to
`/login`.

## 5. Running the test suites

```bash
# Backend — from backend/
uv run pytest tests

# Frontend — from frontend/
npm run typecheck
npm run lint
npm run test
```

## Troubleshooting

See `docs/release/TROUBLESHOOTING_GUIDE.md` for common problems (port
conflicts, migration failures, a blank frontend page, WebSocket
connection failures, etc.).

## Next steps

- `docs/release/DEPLOYMENT_GUIDE.md` — running this in production
- `docs/release/ADMINISTRATOR_GUIDE.md` — operating a running deployment
- `docs/release/USER_GUIDE.md` — using the application once it's running
- `docs/architecture/ARCHITECTURE_OVERVIEW.md` — how the whole system fits together
