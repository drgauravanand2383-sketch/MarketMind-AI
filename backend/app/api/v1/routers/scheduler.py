"""Scheduler health endpoint — `GET /system/scheduler`.

Read-only introspection of the scheduling subsystem: what's registered,
whether the APScheduler timer is running, and — the reason this endpoint
exists — whether it is actually *dispatching*. `scheduler_running` alone
is a synchronous "`.start()` was called" flag; a rare startup race can
leave it `True` while no job fires for hours. `dispatching` (backed by
`APSchedulerService`'s internal canary) is the honest signal, and
`watchdog_recoveries` counts how often the watchdog has had to rebuild
the scheduler.

Reuses `APSchedulerService.health_check()` — no scheduling state is
recomputed here. 503 when the scheduling subsystem is disabled on this
instance (`SCHEDULER_ENABLED=false`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.dependencies.state import get_ap_scheduler_service
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.scheduler.ap_scheduler import APSchedulerService
from app.scheduler.models import SchedulerHealthStatus

__all__ = ["router"]

router = APIRouter(tags=["System"])


@router.get(
    "/system/scheduler",
    response_model=SuccessResponse[SchedulerHealthStatus],
    summary="Scheduler subsystem health",
    description=(
        "Registration counts plus the live APScheduler state — `scheduler_running`, "
        "`dispatching` (canary-backed proof the timer loop is alive), `last_execution`, "
        "`next_execution`, and `watchdog_recoveries`. No workflow is executed to produce this."
    ),
    responses={
        200: {"description": "Health computed (the body may still report `dispatching=false`)."},
        503: {"description": "The scheduling subsystem is disabled on this instance."},
    },
)
async def get_scheduler_health(
    request: Request,
    ap_scheduler_service: APSchedulerService = Depends(get_ap_scheduler_service),
) -> SuccessResponse[SchedulerHealthStatus]:
    status = await ap_scheduler_service.health_check()
    return build_success_response(status, request)
