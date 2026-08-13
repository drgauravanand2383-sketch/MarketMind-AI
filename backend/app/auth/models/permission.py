"""Permission domain model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Permission"]


class Permission(BaseModel):
    """One named permission. No fixed catalog of permissions is defined
    by this framework — a deployment defines whichever it needs; this
    model only gives each one a stable id/name/description."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
