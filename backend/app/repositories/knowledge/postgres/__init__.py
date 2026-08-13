"""PostgreSQL-backed knowledge repository (SQLAlchemy async ORM)."""

from app.repositories.knowledge.postgres.models import Base, KnowledgeRecordModel
from app.repositories.knowledge.postgres.repository import PostgresKnowledgeRepository

__all__ = ["PostgresKnowledgeRepository", "Base", "KnowledgeRecordModel"]
