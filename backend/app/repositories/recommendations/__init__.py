"""Recommendation Repository: persistence contract for the Portfolio
Recommendation Engine.

No database implementation and no business rules exist in this package's
top level — abstract interface only.
"""

from app.repositories.recommendations.repository import BaseRecommendationRepository

__all__ = ["BaseRecommendationRepository"]
