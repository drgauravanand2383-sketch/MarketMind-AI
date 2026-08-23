"""Tests for the Idempotency Abstraction (Sprint 60) — the interface
contract, the `Idempotency-Key` header dependency, and the request
fingerprint helper. No concrete `IdempotencyStore` implementation ships
this sprint ("No persistence implementation required."); `_FakeIdempotencyStore`
here is a test-only double proving the interface is implementable.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.idempotency import (
    IdempotencyRecord,
    IdempotencyStore,
    compute_request_fingerprint,
    get_idempotency_key,
)

NOW = datetime(2026, 8, 8, tzinfo=UTC)


class _FakeIdempotencyStore(IdempotencyStore):
    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}

    async def get(self, key: str) -> IdempotencyRecord | None:
        return self._records.get(key)

    async def put(self, record: IdempotencyRecord) -> None:
        self._records[record.key] = record


def _record(key: str = "k1", fingerprint: str = "fp1") -> IdempotencyRecord:
    return IdempotencyRecord(
        key=key, request_fingerprint=fingerprint, status_code=201, response_body='{"ok": true}', created_at=NOW
    )


def test_idempotency_store_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        IdempotencyStore()  # type: ignore[abstract]


def test_idempotency_record_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IdempotencyRecord(
            key="k1", request_fingerprint="fp1", status_code=201, response_body="{}", created_at=NOW, bogus=True
        )


def test_idempotency_record_requires_a_non_blank_key() -> None:
    with pytest.raises(ValidationError):
        IdempotencyRecord(key="", request_fingerprint="fp1", status_code=201, response_body="{}", created_at=NOW)


async def test_fake_store_round_trips_a_record() -> None:
    store = _FakeIdempotencyStore()
    record = _record()

    assert await store.get("k1") is None
    await store.put(record)
    fetched = await store.get("k1")

    assert fetched == record


async def test_fake_store_returns_none_for_unknown_key() -> None:
    store = _FakeIdempotencyStore()
    assert await store.get("never-stored") is None


# --------------------------------------------------------------------------
# Idempotency-Key header extraction
# --------------------------------------------------------------------------


def test_get_idempotency_key_reads_the_header() -> None:
    app = FastAPI()

    @app.post("/probe")
    async def probe(key: str | None = Depends(get_idempotency_key)) -> dict:
        return {"key": key}

    with TestClient(app) as client:
        with_header = client.post("/probe", headers={"Idempotency-Key": "abc-123"})
        without_header = client.post("/probe")

    assert with_header.json()["key"] == "abc-123"
    assert without_header.json()["key"] is None


# --------------------------------------------------------------------------
# Request fingerprint
# --------------------------------------------------------------------------


def test_fingerprint_is_stable_for_identical_requests() -> None:
    first = compute_request_fingerprint(method="post", path="/api/v1/watchlists", body=b'{"name":"x"}')
    second = compute_request_fingerprint(method="POST", path="/api/v1/watchlists", body=b'{"name":"x"}')
    assert first == second  # method casing must not matter


def test_fingerprint_differs_for_different_bodies() -> None:
    first = compute_request_fingerprint(method="POST", path="/api/v1/watchlists", body=b'{"name":"x"}')
    second = compute_request_fingerprint(method="POST", path="/api/v1/watchlists", body=b'{"name":"y"}')
    assert first != second


def test_fingerprint_differs_for_different_paths() -> None:
    first = compute_request_fingerprint(method="POST", path="/api/v1/watchlists", body=b"{}")
    second = compute_request_fingerprint(method="POST", path="/api/v1/strategies", body=b"{}")
    assert first != second
