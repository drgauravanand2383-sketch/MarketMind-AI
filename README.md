# MarketMind AI

MarketMind AI is a personal market intelligence platform built on **MarketMind OS** — a modular AI operating system for domain-specific, multi-agent AI products.

## Overview

MarketMind AI ingests market data and financial news, analyzes it across multiple dimensions (technical, fundamental, sentiment, risk), and delivers synthesized intelligence through a daily morning brief, conversational chat, and on-demand reports — powered by a coordinated team of specialized AI agents.

## Tech Stack

- **Language:** Python 3.13
- **Backend Framework:** FastAPI
- **Package Manager:** uv
- **Agent Orchestration:** LangGraph
- **LLM:** Claude API
- **Relational Database:** PostgreSQL
- **Cache / Queue:** Redis
- **Vector Store:** ChromaDB
- **Frontend:** Next.js
- **Containerization:** Docker / Docker Compose

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- Node.js (for the frontend, added in a later sprint)

## Getting Started

1. Clone the repository.
2. Copy the environment template and fill in real values:
   ```
   cp .env.example .env
   ```
3. Start the infrastructure services (PostgreSQL, Redis, ChromaDB):
   ```
   docker compose up -d
   ```
4. Install backend dependencies:
   ```
   cd backend
   uv sync
   ```

## Project Structure

See [`docs/architecture/`](docs/architecture/) for the full architecture overview and [`CLAUDE.md`](CLAUDE.md) for project governance and development rules.

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — Project constitution and rules of engagement
- [`docs/`](docs/) — Architecture, agents, workflows, API, database, prompts, decisions, and roadmap documentation

## Status

Sprint 1 — Foundational setup in progress.
