"""Explainability Repository: persistence contract for the Explainability
& Performance Attribution Engine.

No database implementation and no business rules exist in this package's
top level — abstract interface only.
"""

from app.repositories.explainability.repository import BaseExplainabilityRepository

__all__ = ["BaseExplainabilityRepository"]
