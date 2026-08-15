# MarketMind AI

MarketMind AI is a personal market intelligence platform built on **MarketMind OS** — a modular AI operating system for domain-specific, multi-agent AI products.

## Overview

MarketMind AI ingests market data and financial news, resolves it to canonical companies, and analyzes it across multiple dimensions (technical, risk, strategy, recommendations, signals, alerts) — delivering synthesized intelligence through a Decision Center UI, real-time WebSocket notifications, and a proactive Continuous Intelligence layer that detects and surfaces meaningful changes on its own, without waiting to be asked.

## Tech Stack

- **Language:** Python 3.13
- **Backend Framework:** FastAPI
- **Package Manager:** uv
- **Agent Orchestration:** LangGraph
- **LLM:** Claude API
- **Relational Database:** PostgreSQL
- **Cache / Queue:** Redis (provisioned; not yet consumed by any current feature)
- **Vector Store:** ChromaDB
- **Live Market Data:** Yahoo Finance (`app/providers/market_data`)
- **Frontend:** React + Vite (TypeScript)
- **Containerization:** Docker / Docker Compose

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Node.js 22+ (for the frontend)
- Docker and Docker Compose

## Getting Started

The fastest path is the full Docker stack — see
[`docs/release/INSTALLATION_GUIDE.md`](docs/release/INSTALLATION_GUIDE.md)
and [`docs/release/DEPLOYMENT_GUIDE.md`](docs/release/DEPLOYMENT_GUIDE.md)
for complete, current instructions (environment variables, migrations,
and verification steps). Summary:

1. Clone the repository.
2. Copy the environment template and fill in real values:
   ```
   cp .env.example .env
   ```
3. Build and start the full stack (PostgreSQL, Redis, ChromaDB, backend, frontend):
   ```
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
4. Apply database migrations:
   ```
   docker compose exec backend python -m alembic upgrade head
   ```
5. Verify: `curl http://localhost:8000/api/v1/health` and open `http://localhost:8080`.

For native (non-Docker) backend development: `cd backend && uv sync`.
For native frontend development: `cd frontend && npm install && npm run dev`.

## Project Structure

See [`docs/architecture/`](docs/architecture/) for the full architecture overview and [`CLAUDE.md`](CLAUDE.md) for project governance and development rules.

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — Project constitution and rules of engagement
- [`docs/architecture/`](docs/architecture/) — System design, one document per major subsystem/milestone
- [`docs/release/`](docs/release/) — Installation, deployment, security, operations, and release documentation
- [`docs/database/MIGRATIONS.md`](docs/database/MIGRATIONS.md) — Migration history and conventions

## Status

v1.0.0 is released. Post-v1.0 work (Milestones 11–16) added live market
data, entity resolution, portfolio intelligence, continuous/proactive
intelligence, and durable persistence for that intelligence layer. A
v1.1 Release Candidate is in preparation — see
[`docs/release/KNOWN_LIMITATIONS.md`](docs/release/KNOWN_LIMITATIONS.md)
for exactly what is and isn't covered, and
[`docs/release/RELEASE_CHECKLIST_V1_1.md`](docs/release/RELEASE_CHECKLIST_V1_1.md)
for current RC verification status.
