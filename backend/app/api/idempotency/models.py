"""Provider-independent data shapes for the idempotency abstraction
(Sprint 60). No concrete `IdempotencyStore` implementation ships this
sprint ("No persistence implementation required.") — mirrors the same
interface-only precedent `app.api.rate_limiting.models` follows.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["IdempotencyRecord"]


class IdempotencyRecord(BaseModel):
    """One previously-completed request, stored under its idempotency
    key so a duplicate submission can be answered with the original
    response instead of repeating the underlying operation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    request_fingerprint: str = Field(
        min_length=1,
        description="A hash of method+path+body (see app.api.idempotency.fingerprint) — lets an "
        "implementation detect a key reused for a genuinely different request rather than silently "
        "replaying the wrong response.",
    )
    status_code: int = Field(ge=100, le=599)
    response_body: str
    created_at: datetime
