"""Screening Engine: evaluates companies against reusable investment
screening criteria.

Data-source agnostic — accepts structured `CompanyMetrics` objects and
determines whether they satisfy user-defined `ScreeningProfile` rules. No
live API or market-data connection of any kind lives here.
"""

from __future__ import annotations

from app.screening.exceptions import (
    DuplicateProfileNameError,
    MaxFiltersExceededError,
    ScreeningError,
    ScreeningProfileNotFoundError,
)
from app.screening.models import (
    CompanyMetrics,
    FilterEvaluation,
    LogicalGroup,
    LogicType,
    ScreenFilter,
    ScreeningProfile,
    ScreenOperator,
    ScreenResult,
)
from app.screening.engine import ScreeningEngine

__all__ = [
    "ScreeningEngine",
    "ScreenOperator",
    "LogicType",
    "ScreenFilter",
    "LogicalGroup",
    "ScreeningProfile",
    "FilterEvaluation",
    "ScreenResult",
    "CompanyMetrics",
    "ScreeningError",
    "ScreeningProfileNotFoundError",
    "DuplicateProfileNameError",
    "MaxFiltersExceededError",
]
