"""Knowledge Repository: persistence and retrieval contracts for the Knowledge Hub.

No database, ChromaDB, SQL, or embedding-generation implementation exists
in this package — abstract interfaces only.
"""

from app.repositories.knowledge.models import (
    DeleteResult,
    KnowledgeRecord,
    SaveResult,
    SearchQuery,
    SearchResult,
)
from app.repositories.knowledge.repository import BaseKnowledgeRepository

__all__ = [
    "BaseKnowledgeRepository",
    "SaveResult",
    "SearchQuery",
    "SearchResult",
    "KnowledgeRecord",
    "DeleteResult",
]
