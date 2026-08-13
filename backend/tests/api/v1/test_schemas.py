"""Tests for the shared response-envelope schemas: SuccessResponse,
ErrorResponse, ValidationErrorResponse, PaginatedResponse, MetadataResponse."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, ValidationError

from app.api.v1.schemas.common import (
    ErrorResponse,
    MetadataResponse,
    PaginatedResponse,
    SuccessResponse,
    ValidationErrorFieldError,
    ValidationErrorResponse,
    build_metadata,
    build_success_response,
)

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


class _Payload(BaseModel):
    value: int


# --- MetadataResponse -----------------------------------------------------------


def test_metadata_response_defaults_api_version_to_v1() -> None:
    meta = MetadataResponse(request_id="r1", timestamp=NOW)

    assert meta.api_version == "v1"


def test_build_metadata_uses_provided_timestamp() -> None:
    meta = build_metadata("r1", now=NOW)

    assert meta.timestamp == NOW
    assert meta.request_id == "r1"


def test_build_metadata_defaults_to_current_time() -> None:
    meta = build_metadata("r1")

    assert meta.timestamp is not None


# --- SuccessResponse -----------------------------------------------------------


def test_success_response_wraps_typed_data() -> None:
    response = SuccessResponse[_Payload](data=_Payload(value=5), meta=build_metadata("r1", now=NOW))

    assert response.data.value == 5
    assert response.meta.request_id == "r1"


def test_success_response_serializes_to_json_cleanly() -> None:
    response = SuccessResponse[_Payload](data=_Payload(value=5), meta=build_metadata("r1", now=NOW))

    dumped = response.model_dump(mode="json")
    assert dumped["data"]["value"] == 5
    assert dumped["meta"]["request_id"] == "r1"


# --- ErrorResponse -----------------------------------------------------------


def test_error_response_requires_error_and_message() -> None:
    response = ErrorResponse(error="not_found", message="x", meta=build_metadata("r1", now=NOW))

    assert response.error == "not_found"
    assert response.message == "x"


def test_error_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ErrorResponse(error="x", message="y", meta=build_metadata("r1", now=NOW), unexpected="z")


# --- ValidationErrorResponse -----------------------------------------------------------


def test_validation_error_response_defaults() -> None:
    response = ValidationErrorResponse(meta=build_metadata("r1", now=NOW))

    assert response.error == "validation_error"
    assert response.details == ()


def test_validation_error_response_carries_field_details() -> None:
    detail = ValidationErrorFieldError(location=("query", "count"), message="field required", type="missing")
    response = ValidationErrorResponse(details=(detail,), meta=build_metadata("r1", now=NOW))

    assert response.details[0].location == ("query", "count")


# --- PaginatedResponse -----------------------------------------------------------


def test_paginated_response_accepts_valid_fields() -> None:
    response = PaginatedResponse[_Payload](
        data=(_Payload(value=1), _Payload(value=2)), total=2, page=1, page_size=10,
        meta=build_metadata("r1", now=NOW),
    )

    assert len(response.data) == 2
    assert response.total == 2


def test_paginated_response_rejects_non_positive_page() -> None:
    with pytest.raises(ValidationError):
        PaginatedResponse[_Payload](data=(), total=0, page=0, page_size=10, meta=build_metadata("r1", now=NOW))


def test_paginated_response_rejects_negative_total() -> None:
    with pytest.raises(ValidationError):
        PaginatedResponse[_Payload](data=(), total=-1, page=1, page_size=10, meta=build_metadata("r1", now=NOW))


# --- build_success_response -----------------------------------------------------------


def test_build_success_response_uses_request_state_id() -> None:
    class _FakeState:
        request_id = "from-middleware"

    class _FakeRequest:
        state = _FakeState()

    response = build_success_response(_Payload(value=1), _FakeRequest())  # type: ignore[arg-type]

    assert response.meta.request_id == "from-middleware"


def test_build_success_response_generates_id_when_absent() -> None:
    class _FakeState:
        pass

    class _FakeRequest:
        state = _FakeState()

    response = build_success_response(_Payload(value=1), _FakeRequest())  # type: ignore[arg-type]

    assert response.meta.request_id
