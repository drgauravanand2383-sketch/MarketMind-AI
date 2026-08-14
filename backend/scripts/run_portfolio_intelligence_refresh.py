"""Operational trigger for Portfolio Market Intelligence (Milestone 14).

Run this to recompute a live market snapshot for every existing portfolio
(watchlist) on demand ("run now") — the same operational pattern
`scripts/run_market_data_refresh.py` (Milestone 13) and
`scripts/run_entity_backfill.py` (Milestone 12) already establish. Not
exposed over HTTP anywhere: only reachable by whoever can already run a
command inside the backend container/environment.

Deliberately does NOT invoke `PortfolioIntelligenceAgent` (the LLM-narrated
report `GET /portfolio/intelligence` returns) for every portfolio — that
would mean an unbounded number of real Claude API calls per run, one per
existing portfolio, on every operator invocation, for no cache/freshness
benefit (the agent is not market-data-driven; nothing about its narrative
goes stale the way a price quote does). "Recompute portfolio intelligence"
here is scoped to what Milestone 14 actually added: live per-company
market data (`PortfolioMarketSnapshotService`, reusing Milestone 13's own
cache/provider — no new network surface). This mirrors
`run_market_data_refresh.py`'s own scope exactly, just aggregated per
portfolio instead of across the flat Milestone 12 entity list.

Unlike `run_market_data_refresh.py`, this is not tied to a Scheduler
registration — there is no fixed, portfolio-agnostic entity set to poll on
an interval the way Milestone 12's canonical reference set is; portfolios
are user-created and arbitrary. This script is a pure "run now, over every
portfolio that currently exists" trigger, exactly like
`run_entity_backfill.py`'s own un-scheduled shape.

Usage (matches the existing `docker compose exec backend ...` convention):

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
        exec backend python scripts/run_portfolio_intelligence_refresh.py

Or natively, from `backend/`:

    uv run python scripts/run_portfolio_intelligence_refresh.py

Prints a JSON summary to stdout (per-portfolio fresh/stale/unavailable/
unmapped counts, and the individually-identifiable stale/unavailable/
unmapped entities — never just a count) and exits 0 on success (including
zero portfolios existing), 1 if `portfolio_market_snapshot_service` or
`watchlist_service` isn't configured on this deployment. Never prints a
token, password, or any `.env` value.
"""

from __future__ import annotations

import asyncio
import json
import sys

from fastapi import FastAPI

from app.bootstrap import bootstrap_application_state, shutdown_application_state
from app.services.market_snapshot.models import MarketSnapshotStatus
from app.services.portfolio_market_snapshot.models import PortfolioMarketSnapshot


def _summarize(snapshot: PortfolioMarketSnapshot, portfolio_name: str) -> dict[str, object]:
    needs_attention = [
        {"entity_id": item.entity_id, "status": item.status.value, "reason": item.reason}
        for item in snapshot.company_snapshots
        if item.status != MarketSnapshotStatus.FRESH
    ]
    return {
        "portfolio_id": snapshot.portfolio_id,
        "portfolio_name": portfolio_name,
        "fresh_count": snapshot.fresh_count,
        "stale_count": snapshot.stale_count,
        "unavailable_count": snapshot.unavailable_count,
        "entity_not_mapped_count": snapshot.entity_not_mapped_count,
        "needs_attention": needs_attention,
    }


async def _run() -> int:
    app = FastAPI()
    await bootstrap_application_state(app)
    try:
        watchlist_service = getattr(app.state, "watchlist_service", None)
        market_snapshot_service = getattr(app.state, "portfolio_market_snapshot_service", None)

        if watchlist_service is None or market_snapshot_service is None:
            print(
                json.dumps(
                    {
                        "status": "unavailable",
                        "reason": (
                            "watchlist_service or portfolio_market_snapshot_service is not "
                            "configured on this application instance."
                        ),
                    }
                )
            )
            return 1

        watchlists = await watchlist_service.list_watchlists()
        portfolios = []
        for watchlist in watchlists:
            snapshot = await market_snapshot_service.get_portfolio_snapshot(watchlist)
            portfolios.append(_summarize(snapshot, watchlist.name))

        print(
            json.dumps(
                {"status": "ok", "portfolios_processed": len(portfolios), "portfolios": portfolios},
                indent=2,
            )
        )
        return 0
    finally:
        await shutdown_application_state(app)


def main() -> None:
    exit_code = asyncio.run(_run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
