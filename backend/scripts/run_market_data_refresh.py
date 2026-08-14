"""Operational trigger for the Market Data Refresh workflow (Milestone 13).

Run this to refresh market snapshots for every canonical entity in the
Milestone 12 reference set on demand ("run now") — the same operational
pattern `scripts/run_ingestion.py` (Milestone 11) and
`scripts/run_entity_backfill.py` (Milestone 12) already establish. Not
exposed over HTTP anywhere: only reachable by whoever can already run a
command inside the backend container/environment.

Usage (matches the existing `docker compose exec backend ...` convention):

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
        exec backend python scripts/run_market_data_refresh.py

Or natively, from `backend/`:

    uv run python scripts/run_market_data_refresh.py

Prints a JSON summary to stdout (execution id, status, entities
requested, fresh/stale/unavailable counts, and the per-entity results —
so a stale or unavailable symbol is individually identifiable, not just
counted) and exits 0 on success, 1 if the workflow isn't registered
(entity_resolution_service unavailable), disabled
(`MARKET_DATA_ENABLED` is not `true`), or failed outright. Never prints a
token, password, or any `.env` value — only aggregate/per-entity counts
and statuses from the run's own MarketDataRefreshResult.
"""

from __future__ import annotations

import asyncio
import json
import sys

from fastapi import FastAPI

from app.bootstrap import (
    MARKET_DATA_WORKFLOW_ID,
    bootstrap_application_state,
    shutdown_application_state,
)
from app.scheduler.scheduler import ScheduleDisabledError, ScheduleNotRegisteredError
from app.workflows.market_data_refresh.models import MarketDataRefreshResult


def _summarize(result: MarketDataRefreshResult) -> dict[str, object]:
    stale_or_unavailable = [
        {"entity_id": r.entity_id, "status": r.status.value, "reason": r.reason}
        for r in result.results
        if r.status.value not in ("FRESH",)
    ]
    return {
        "execution_id": result.execution_id,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "entities_requested": result.entities_requested,
        "fresh_count": result.fresh_count,
        "stale_count": result.stale_count,
        "unavailable_count": result.unavailable_count,
        "stale_or_unavailable": stale_or_unavailable,
    }


async def _run() -> int:
    app = FastAPI()
    await bootstrap_application_state(app)
    try:
        scheduler = app.state.scheduler
        try:
            record = await scheduler.run_schedule(MARKET_DATA_WORKFLOW_ID)
        except ScheduleNotRegisteredError:
            print(
                json.dumps(
                    {
                        "status": "unavailable",
                        "reason": (
                            "Market Data Refresh is not registered — entity_resolution_service "
                            "was unavailable at startup (see the backend's own startup logs)."
                        ),
                    }
                )
            )
            return 1
        except ScheduleDisabledError:
            print(
                json.dumps(
                    {
                        "status": "disabled",
                        "reason": "MARKET_DATA_ENABLED is not set to true.",
                    }
                )
            )
            return 1

        execution_result = record.result
        output_is_valid = isinstance(execution_result.output, MarketDataRefreshResult)
        if not execution_result.success or not output_is_valid:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "execution_id": record.execution_id,
                        "error": execution_result.error,
                    }
                )
            )
            return 1

        summary = _summarize(execution_result.output)
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        await shutdown_application_state(app)


def main() -> None:
    exit_code = asyncio.run(_run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
