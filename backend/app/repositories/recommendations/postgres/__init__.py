"""PostgreSQL-backed recommendation repository (SQLAlchemy async ORM)."""

from app.repositories.recommendations.postgres.models import (
    Base,
    RecommendationRequestModel,
    RecommendationResultModel,
)
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository

__all__ = [
    "PostgresRecommendationRepository",
    "Base",
    "RecommendationRequestModel",
    "RecommendationResultModel",
]
