"""Schemas for the production KnowledgeHub service."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["KnowledgeSearchFilters"]


class KnowledgeSearchFilters(BaseModel):
    """Structured retrieval filters for KnowledgeHub.search().

    If none of `company`/`provider`/`source`/`start_date`/`end_date` are
    set, KnowledgeHub treats the request as unstructured and routes it to
    semantic retrieval instead — see hub.py's routing rules.
    """

    model_config = ConfigDict(extra="forbid")

    company: str | None = None
    provider: str | None = None
    source: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    top_k: int = Field(default=5, ge=1)

    @model_validator(mode="after")
    def _validate_date_range(self) -> KnowledgeSearchFilters:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not be after end_date")
        return self
