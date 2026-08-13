"""HTTP-layer request schema for the Alert API.

Response bodies reuse `app.alerts.models` directly (`Alert`, `AlertBatch`).

There is no REST endpoint (in this sprint or any earlier one) for creating
`AlertRule`s or for producing a `SignalResult`, so `POST /alerts/evaluate`
cannot reference either purely by id and expect the server to already have
the data — the request carries the `SignalResult`(s) inline
(`app.signals.models.SignalResult`, reused directly) and references
pre-existing `AlertRule`s by id, resolved via `AlertService.get_rule()`/
`.list_rules()`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.signals.models import SignalResult

__all__ = ["EvaluateAlertsRequest"]


class EvaluateAlertsRequest(BaseModel):
    """Request body for `POST /api/v1/alerts/evaluate`."""

    model_config = ConfigDict(extra="forbid")

    signals: list[SignalResult] = Field(
        min_length=1,
        examples=[
            [
                {
                    "ticker": "AAPL", "signal_name": "RSI Oversold", "category": "TECHNICAL",
                    "triggered": True, "confidence": 90.0, "score": 82.0, "priority": "HIGH",
                    "reason": "RSI below 30", "timestamp": "2026-08-08T00:00:00Z",
                }
            ]
        ],
    )
    rule_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        examples=[["9c1e2b1a-3f4d-4a5e-8b6c-7d8e9f0a1b2c"]],
        description="Alert rules to evaluate against. Empty means every enabled rule.",
    )
