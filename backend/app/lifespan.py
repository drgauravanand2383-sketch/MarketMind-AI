"""FastAPI lifespan wiring for MarketMind AI.

Runs Application Bootstrap on startup and releases resources on shutdown.
Contains no business, agent, or API logic itself — only lifecycle
plumbing around `bootstrap.py`'s composition root.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bootstrap import bootstrap_application_state, shutdown_application_state

__all__ = ["lifespan"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bootstrap application state on startup; release it on shutdown."""
    await bootstrap_application_state(app)
    try:
        yield
    finally:
        await shutdown_application_state(app)
