"""Continuous Intelligence State Repository: persistence contract for
comparison state, suppression, and cycle-lock claims (Milestone 16).

No database implementation and no business rules exist in this package's
top level — abstract interface only.
"""

from app.repositories.continuous_intelligence.repository import (
    BaseContinuousIntelligenceStateRepository,
)

__all__ = ["BaseContinuousIntelligenceStateRepository"]
