"""Shared helpers for Screening Engine tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.screening.models import LogicalGroup, ScreenFilter, ScreeningProfile, ScreenOperator

NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


def make_filter(
    filter_id: str = "f1",
    field: str = "pe_ratio",
    operator: ScreenOperator = ScreenOperator.LESS_THAN,
    value: object = 20,
    group: str | None = None,
    enabled: bool = True,
) -> ScreenFilter:
    return ScreenFilter(
        id=filter_id, field=field, operator=operator, value=value, group=group, enabled=enabled
    )


def make_profile(
    profile_id: str = "p1",
    name: str = "Test Profile",
    filters: tuple[ScreenFilter, ...] = (),
    groups: tuple[LogicalGroup, ...] = (),
    **overrides: object,
) -> ScreeningProfile:
    defaults: dict[str, object] = {
        "id": profile_id,
        "name": name,
        "created_at": NOW,
        "updated_at": NOW,
        "filters": filters,
        "groups": groups,
    }
    defaults.update(overrides)
    return ScreeningProfile(**defaults)
