"""Idempotency Abstraction (Sprint 60) — reusable support for `POST`
operations that want `Idempotency-Key`-based duplicate-request detection.
No persistence implementation ships this sprint ("No persistence
implementation required.")."""

from app.api.idempotency.fingerprint import compute_request_fingerprint
from app.api.idempotency.header import IDEMPOTENCY_KEY_HEADER, get_idempotency_key
from app.api.idempotency.models import IdempotencyRecord
from app.api.idempotency.store import IdempotencyStore

__all__ = [
    "IdempotencyStore",
    "IdempotencyRecord",
    "IDEMPOTENCY_KEY_HEADER",
    "get_idempotency_key",
    "compute_request_fingerprint",
]
