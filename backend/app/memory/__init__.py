"""Memory Service — the production, in-process implementation of `MemoryInterface`.

`MemoryService` (service.py) stores and retrieves workflow-, conversation-,
user-, agent-, and global-scoped memory entries (models.py). It is
completely independent of KnowledgeHub and WorkflowEngine: no reasoning,
summarization, or knowledge retrieval is implemented here.

`BaseMemoryStore` / `InProcessMemoryStore` (the internal storage
abstraction) are available from `app.memory.service` directly if needed,
but are not re-exported here — this package's public surface is exactly
the seven names below.
"""

from app.memory.models import (
    MemoryEntry,
    MemoryHealthStatus,
    MemoryQuery,
    MemoryResult,
    MemoryScope,
    MemoryTerm,
)
from app.memory.service import MemoryService

__all__ = [
    "MemoryService",
    "MemoryEntry",
    "MemoryScope",
    "MemoryTerm",
    "MemoryQuery",
    "MemoryResult",
    "MemoryHealthStatus",
]
