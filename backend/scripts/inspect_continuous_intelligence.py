"""Read-only operational diagnostics for Continuous Intelligence (Milestone 16 §15).

Prints the current durable state — comparison-state entries per domain,
suppression entries (with remaining cooldown), the cycle lock's current
claim (held/stale/free), and overall scheduler health — without executing
a cycle or mutating anything. Not exposed over HTTP anywhere: only
reachable by whoever can already run a command inside the backend
container/environment, the same boundary `scripts/run_continuous_intelligence.py`
already establishes.

Usage (matches the existing `docker compose exec backend ...` convention):

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
        exec backend python scripts/inspect_continuous_intelligence.py

Or natively, from `backend/`:

    uv run python scripts/inspect_continuous_intelligence.py

Prints a JSON summary to stdout and exits 0, unless the durable repository
itself is unreachable (exit 1) — a healthy in-memory-only deployment
(no Postgres repository configured) is reported, not treated as an error,
since that is a valid, documented configuration (§2/§3/§5).
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI

from app.bootstrap import bootstrap_application_state, shutdown_application_state

_STATE_DOMAINS = (
    "MARKET", "MARKET_STATUS", "NEWS", "NEWS_CONFIDENCE",
    "RISK_SEVERITY", "RECOMMENDATION", "STRATEGY_ALIGNMENT", "SIGNAL_TRIGGERED",
)
_SUPPRESSION_DOMAIN = "SUPPRESSION"
_LOCK_DOMAIN = "LOCK"
_MAX_ENTRIES_PER_DOMAIN = 25


def _serialize_row(key: str, value: Any, observed_at: datetime) -> dict[str, object]:
    return {"key": key, "value": value, "observed_at": observed_at.isoformat()}


async def _inspect(app: FastAPI) -> dict[str, object]:
    repository = getattr(app.state, "continuous_intelligence_repository", None)
    settings = app.state.settings

    if repository is None:
        return {
            "status": "in_memory_only",
            "reason": (
                "No durable Continuous Intelligence repository configured (Postgres unreachable or "
                "not configured) — comparison state, suppression, and cycle locking are in-memory only "
                "for this process, and will not survive a restart (§4). This is a valid, documented "
                "configuration, not an error."
            ),
        }

    now = datetime.now(UTC)
    state_summary: dict[str, object] = {}
    for domain in _STATE_DOMAINS:
        rows = await repository.list_domain(domain)
        state_summary[domain] = {
            "entry_count": len(rows),
            "most_recent": [_serialize_row(k, v, ts) for k, v, ts in rows[:_MAX_ENTRIES_PER_DOMAIN]],
        }

    cooldown_minutes = settings.continuous_intelligence_suppression_cooldown_minutes
    suppression_rows = await repository.list_domain(_SUPPRESSION_DOMAIN)
    suppression_summary = {
        "entry_count": len(suppression_rows),
        "cooldown_minutes": cooldown_minutes,
        "recent_fingerprints": [
            {
                "fingerprint": key,
                "emitted_at": observed_at.isoformat(),
                "cooldown_remaining_minutes": max(
                    0.0, cooldown_minutes - (now - observed_at).total_seconds() / 60
                ),
            }
            for key, _, observed_at in suppression_rows[:_MAX_ENTRIES_PER_DOMAIN]
        ],
    }

    lock_ttl_seconds = settings.continuous_intelligence_lock_ttl_seconds
    lock_rows = await repository.list_domain(_LOCK_DOMAIN)
    lock_summary: dict[str, object]
    if not lock_rows:
        lock_summary = {"status": "free"}
    else:
        key, value, observed_at = lock_rows[0]
        age_seconds = (now - observed_at).total_seconds()
        lock_summary = {
            "status": "stale (will be reclaimed by the next cycle)" if age_seconds >= lock_ttl_seconds else "held",
            "key": key,
            "holder": value.get("holder") if isinstance(value, dict) else None,
            "claimed_at": observed_at.isoformat(),
            "age_seconds": age_seconds,
            "lock_ttl_seconds": lock_ttl_seconds,
        }

    scheduler_health: dict[str, object] | None = None
    ap_scheduler_service = getattr(app.state, "ap_scheduler_service", None)
    if ap_scheduler_service is not None:
        health = await ap_scheduler_service.health_check()
        scheduler_health = {
            "scheduler_running": health.scheduler_running,
            "registered_schedules": health.registered_schedules,
            "enabled_schedules": health.enabled_schedules,
            "last_execution": health.last_execution.isoformat() if health.last_execution else None,
            "next_execution": health.next_execution.isoformat() if health.next_execution else None,
        }

    return {
        "status": "ok",
        "checked_at": now.isoformat(),
        "state": state_summary,
        "suppression": suppression_summary,
        "lock": lock_summary,
        "scheduler": scheduler_health,
    }


async def _run() -> int:
    app = FastAPI()
    await bootstrap_application_state(app)
    try:
        repository = getattr(app.state, "continuous_intelligence_repository", None)
        if repository is not None and not await repository.health_check():
            print(
                json.dumps(
                    {"status": "error", "reason": "Continuous Intelligence repository configured but unreachable."}
                )
            )
            return 1
        summary = await _inspect(app)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    finally:
        await shutdown_application_state(app)


def main() -> None:
    exit_code = asyncio.run(_run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
