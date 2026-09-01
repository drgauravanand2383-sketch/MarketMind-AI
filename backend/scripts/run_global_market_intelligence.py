"""Operational trigger for the Global Market Intelligence workflow.

Run this to execute the daily Global Market Intelligence workflow once, on
demand ("run now") — the same operational pattern
`scripts/run_market_data_refresh.py` / `scripts/run_ingestion.py` already
establish. Not exposed over HTTP anywhere (the `/api/v1/global-markets`
router is deliberately read-only): only reachable by whoever can already
run a command inside the backend container/environment.

Usage (matches the existing `docker compose exec backend ...` convention):

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
        exec backend python scripts/run_global_market_intelligence.py

Or natively, from `backend/`:

    uv run python scripts/run_global_market_intelligence.py

Prints a JSON summary to stdout (run id, run_date, overall status, each
of the nine categories' own succeeded/error outcome, and — read back from
the ranked-asset repository — how many ranked assets each category
persisted) and exits 0 on success/partial, 1 if the schedule isn't
registered, is disabled (`GLOBAL_MARKETS_ENABLED` is not `true`), or the
run failed outright. Never prints a token, password, or any `.env` value —
only the run's own IntelligenceRun fields and aggregate per-category
counts.
"""

from __future__ import annotations

import asyncio
import json
import sys

from fastapi import FastAPI

from app.bootstrap import (
    GLOBAL_MARKETS_WORKFLOW_ID,
    bootstrap_application_state,
    shutdown_application_state,
)
from app.global_markets.models import REPORT_CATEGORY_DEFINITIONS, IntelligenceRun
from app.repositories.global_markets.ranked_asset_repository import BaseRankedAssetRepository
from app.scheduler.scheduler import ScheduleDisabledError, ScheduleNotRegisteredError


async def _summarize(run: IntelligenceRun, repository: BaseRankedAssetRepository | None) -> dict[str, object]:
    categories: list[dict[str, object]] = []
    for outcome in run.category_outcomes:
        ranked_count: int | None = None
        if repository is not None and outcome.succeeded:
            ranked_count = len(await repository.list_ranked_assets(run.id, outcome.category))
        categories.append(
            {
                "category": outcome.category.value,
                "display_name": REPORT_CATEGORY_DEFINITIONS[outcome.category].display_name,
                "succeeded": outcome.succeeded,
                "error": outcome.error,
                "ranked_assets_persisted": ranked_count,
            }
        )
    return {
        "run_id": run.id,
        "run_date": run.run_date.isoformat(),
        "status": run.status.value,
        "triggered_by": run.triggered_by,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at is not None else None,
        "categories": categories,
    }


async def _run() -> int:
    app = FastAPI()
    await bootstrap_application_state(app)
    try:
        scheduler = app.state.scheduler
        try:
            record = await scheduler.run_schedule(GLOBAL_MARKETS_WORKFLOW_ID)
        except ScheduleNotRegisteredError:
            print(
                json.dumps(
                    {
                        "status": "unavailable",
                        "reason": (
                            "Global Market Intelligence is not registered — see the backend's own "
                            "startup logs."
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
                        "reason": "GLOBAL_MARKETS_ENABLED is not set to true.",
                    }
                )
            )
            return 1

        execution_result = record.result
        output_is_valid = isinstance(execution_result.output, IntelligenceRun)
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

        summary = await _summarize(
            execution_result.output,
            getattr(app.state, "global_market_ranked_asset_repository", None),
        )
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        await shutdown_application_state(app)


def main() -> None:
    exit_code = asyncio.run(_run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
