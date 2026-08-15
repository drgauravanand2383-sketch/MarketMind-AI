"""Operational trigger for Continuous Intelligence (Milestone 15).

Run this to execute one Continuous Intelligence cycle on demand ("run
now") — the same operational pattern `scripts/run_market_data_refresh.py`
(Milestone 13) already establishes. Not exposed over HTTP anywhere: only
reachable by whoever can already run a command inside the backend
container/environment.

Usage (matches the existing `docker compose exec backend ...` convention):

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
        exec backend python scripts/run_continuous_intelligence.py

Or natively, from `backend/`:

    uv run python scripts/run_continuous_intelligence.py

Prints a JSON summary to stdout (§19 observability — entities examined,
market/news/decision changes detected, events emitted vs suppressed,
notifications published, failures, duration, and every individual
detected/suppressed change so a specific one is identifiable, never just
a count) and exits 0 on success, 1 if the workflow isn't registered
(a required dependency was unavailable at startup — see the backend's own
startup logs), disabled (`CONTINUOUS_INTELLIGENCE_ENABLED` is not `true`),
or the cycle itself reported any failure. Never prints a token, password,
or any `.env` value — only aggregate/per-change counts and summaries from
the run's own `ContinuousIntelligenceCycleResult`.
"""

from __future__ import annotations

import asyncio
import json
import sys

from fastapi import FastAPI

from app.bootstrap import (
    CONTINUOUS_INTELLIGENCE_WORKFLOW_ID,
    bootstrap_application_state,
    shutdown_application_state,
)
from app.scheduler.scheduler import ScheduleDisabledError, ScheduleNotRegisteredError
from app.services.continuous_intelligence.models import ContinuousIntelligenceCycleResult, DetectedChange


def _change_summary(change: DetectedChange) -> dict[str, object]:
    return {
        "domain": change.domain.value,
        "entity_id": change.entity_id,
        "label": change.label,
        "priority": change.priority.value,
        "summary": change.summary,
        "portfolio_id": change.portfolio_id,
    }


def _summarize(result: ContinuousIntelligenceCycleResult) -> dict[str, object]:
    return {
        "execution_id": result.execution_id,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "duration_seconds": result.duration_seconds,
        "entities_examined": result.entities_examined,
        "market_changes_detected": result.market_changes_detected,
        "news_changes_detected": result.news_changes_detected,
        "decision_changes_detected": result.decision_changes_detected,
        "events_emitted": result.events_emitted,
        "events_suppressed": result.events_suppressed,
        "notifications_published": result.notifications_published,
        "failures": list(result.failures),
        "changes": [_change_summary(c) for c in result.changes],
        "suppressed": [_change_summary(c) for c in result.suppressed],
    }


async def _run() -> int:
    app = FastAPI()
    await bootstrap_application_state(app)
    try:
        scheduler = app.state.scheduler
        try:
            record = await scheduler.run_schedule(CONTINUOUS_INTELLIGENCE_WORKFLOW_ID)
        except ScheduleNotRegisteredError:
            print(
                json.dumps(
                    {
                        "status": "unavailable",
                        "reason": (
                            "Continuous Intelligence is not registered — entity_resolution_service or a "
                            "required decision-context service (signal/alert/risk/recommendation) was "
                            "unavailable at startup (see the backend's own startup logs)."
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
                        "reason": "CONTINUOUS_INTELLIGENCE_ENABLED is not set to true.",
                    }
                )
            )
            return 1

        execution_result = record.result
        output_is_valid = isinstance(execution_result.output, ContinuousIntelligenceCycleResult)
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
        return 0 if not summary["failures"] else 1
    finally:
        await shutdown_application_state(app)


def main() -> None:
    exit_code = asyncio.run(_run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
