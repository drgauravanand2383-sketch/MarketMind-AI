"""Extracts the `Idempotency-Key` header — pure HTTP-layer parsing, no
storage or duplicate-detection logic (that lives behind `IdempotencyStore`,
which has no concrete implementation this sprint).
"""

from __future__ import annotations

from fastapi import Header

__all__ = ["IDEMPOTENCY_KEY_HEADER", "get_idempotency_key"]

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"


def get_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_KEY_HEADER),
) -> str | None:
    """FastAPI dependency: the `Idempotency-Key` header value, or `None`
    if the client didn't send one. A router that wants full idempotency
    semantics combines this with a configured `IdempotencyStore` once a
    concrete implementation exists — this dependency alone only reads
    the header, it never checks or stores anything."""
    return idempotency_key
