"""Operational trigger for the Entity Resolution Backfill (Milestone 12).

Run this to resolve entities for already-ingested knowledge records — the
same computation newly-ingested records already get, applied
retroactively. Not exposed over HTTP anywhere: only reachable by whoever
can already run a command inside the backend container/environment,
exactly like `scripts/run_ingestion.py` (Milestone 11) and `alembic
upgrade head` (see `docs/release/DEPLOYMENT_GUIDE.md` §4) — the frozen v1
`/api/v1` surface is never extended for this.

Usage (matches the existing `docker compose exec backend ...` convention):

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
        exec backend python scripts/run_entity_backfill.py [--dry-run] [--batch-size N]

Or natively, from `backend/`:

    uv run python scripts/run_entity_backfill.py --dry-run

Prints a JSON summary to stdout (records processed/updated, per-confidence
-tier counts, errors, duration) and exits 0 on success (including a
completed dry run), 1 if entity resolution or the knowledge repository
isn't configured on this deployment, or if the backfill itself reported
errors. Never prints a token, password, or any `.env` value — only
aggregate counts from the run's own BackfillResult.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from fastapi import FastAPI

from app.bootstrap import bootstrap_application_state, shutdown_application_state
from app.repositories.knowledge.chroma.repository import ChromaKnowledgeRepository
from app.services.entity_resolution.backfill import (
    DEFAULT_BATCH_SIZE,
    EntityResolutionBackfillService,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill entity resolution for existing knowledge records."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and count every record without writing anything.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Records to read/write per page (default: {DEFAULT_BATCH_SIZE}).",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    app = FastAPI()
    await bootstrap_application_state(app)
    try:
        knowledge_repository = app.state.knowledge_repository
        entity_resolution_service = app.state.entity_resolution_service

        if entity_resolution_service is None:
            print(
                json.dumps(
                    {
                        "status": "unavailable",
                        "reason": (
                            "Entity Resolution is not configured — ENTITY_RESOLUTION_ENABLED "
                            "is false, or the configured thresholds are invalid (see the "
                            "backend's own startup logs)."
                        ),
                    }
                )
            )
            return 1
        if not isinstance(knowledge_repository, ChromaKnowledgeRepository):
            print(
                json.dumps(
                    {
                        "status": "unavailable",
                        "reason": (
                            "knowledge_repository is not configured "
                            "(chromadb unreachable at startup)."
                        ),
                    }
                )
            )
            return 1

        backfill = EntityResolutionBackfillService(knowledge_repository, entity_resolution_service)
        result = await backfill.run(batch_size=args.batch_size, dry_run=args.dry_run)

        print(json.dumps(result.model_dump(), indent=2))
        return 0 if not result.errors else 1
    finally:
        await shutdown_application_state(app)


def main() -> None:
    args = _parse_args(sys.argv[1:])
    exit_code = asyncio.run(_run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
