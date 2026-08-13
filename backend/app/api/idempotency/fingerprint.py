"""Computes a stable fingerprint for a request — used to detect when an
`Idempotency-Key` is reused for a genuinely different request (a client
bug, or a key-collision) rather than a legitimate retry of the same
request. A pure function: no I/O, no storage, no business logic.
"""

from __future__ import annotations

import hashlib

__all__ = ["compute_request_fingerprint"]


def compute_request_fingerprint(*, method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode("utf-8"))
    digest.update(b"\n")
    digest.update(path.encode("utf-8"))
    digest.update(b"\n")
    digest.update(body)
    return digest.hexdigest()
