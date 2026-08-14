"""Operational trigger for the Market Intelligence Ingestion pipeline (Milestone 11).

Run this to execute one ingestion run on demand ("run now"), the same way
`alembic upgrade head` is run as a separate, deliberate, non-API step
(see `docs/release/DEPLOYMENT_GUIDE.md` §4) — the frozen v1 `/api/v1`
surface is never extended for this, per this milestone's own constraints.
Not exposed over HTTP anywhere: only reachable by whoever can already run
a command inside the backend container/environment (the same operational
trust boundary Alembic already relies on).

Usage (matches the existing `docker compose exec backend alembic ...`
convention documented in DEPLOYMENT_GUIDE.md §11.2):

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
        exec backend python scripts/run_ingestion.py

Or natively, from `backend/`:

    uv run python scripts/run_ingestion.py

Prints a JSON summary to stdout (run id, status, feeds/articles/embeddings
counts, failures) and exits 0 on a successful pipeline run, 1 otherwise
(including "ingestion is disabled" — set `INGESTION_ENABLED=true` first).
Never prints a token, password, or any `.env` value: only aggregate
counts extracted from the run's own PipelineResult, the same way
`MorningPipeline`'s own `ingestion_run_completed` structured log entry is
built (`app/workflows/morning_pipeline/pipeline.py`).
"""

from __future__ import annotations

import asyncio
import json
import sys

from fastapi import FastAPI

from app.bootstrap import (
    INGESTION_WORKFLOW_ID,
    bootstrap_application_state,
    shutdown_application_state,
)
from app.scheduler.scheduler import ScheduleDisabledError, ScheduleNotRegisteredError
from app.services.knowledge_ingestion.models import RejectionReason
from app.workflows.morning_pipeline.models import PipelineResult


def _summarize(result: PipelineResult) -> dict[str, object]:
    """Build the same aggregate counts `MorningPipeline`'s own
    `ingestion_run_completed` log line reports, read back here from
    `PipelineResult.final_context.agent_outputs` — the per-stage outputs
    the pipeline threads through, not a separately maintained summary."""
    outputs = result.final_context.agent_outputs

    summary: dict[str, object] = {
        "execution_id": result.execution_id,
        "status": result.status.value,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
    }

    collection_result = outputs.get("news_collector")
    if collection_result is not None:
        summary["providers_attempted"] = len(collection_result.provider_summary)
        summary["providers_succeeded"] = sum(1 for s in collection_result.provider_summary if s.success)
        summary["providers_failed"] = sum(1 for s in collection_result.provider_summary if not s.success)
        summary["articles_fetched"] = len(collection_result.items)

    ingestion_batch = outputs.get("knowledge_ingestion")
    if ingestion_batch is not None:
        summary["articles_deduplicated"] = sum(
            1 for item in ingestion_batch.ingestion_metadata.rejected_items
            if item.reason == RejectionReason.DUPLICATE_ID
        )
        summary["articles_rejected_total"] = len(ingestion_batch.ingestion_metadata.rejected_items)

    embedding_result = outputs.get("embedding_provider")
    if embedding_result is not None:
        summary["embeddings_generated"] = embedding_result.total_succeeded
        summary["embedding_failures"] = embedding_result.total_failed

    save_result = outputs.get("knowledge_repository")
    if save_result is not None:
        summary["articles_persisted"] = save_result.vector_count
        if save_result.errors:
            summary["persistence_errors"] = save_result.errors

    if result.failed_stage is not None:
        summary["failed_stage"] = result.failed_stage
        summary["error"] = result.error

    return summary


async def _run() -> int:
    app = FastAPI()
    await bootstrap_application_state(app)
    try:
        scheduler = app.state.scheduler
        try:
            record = await scheduler.run_schedule(INGESTION_WORKFLOW_ID)
        except ScheduleNotRegisteredError:
            print(
                json.dumps(
                    {
                        "status": "unavailable",
                        "reason": (
                            "Market Intelligence Ingestion is not registered — "
                            "embedding_provider or knowledge_repository was unavailable "
                            "at startup (see the backend's own startup logs)."
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
                        "reason": "INGESTION_ENABLED is not set to true.",
                    }
                )
            )
            return 1

        execution_result = record.result
        if not execution_result.success or not isinstance(execution_result.output, PipelineResult):
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
        return 0 if execution_result.output.status.value == "completed" else 1
    finally:
        await shutdown_application_state(app)


def main() -> None:
    exit_code = asyncio.run(_run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
