"""Signal Definition Repository: persistence contract for the Signal Detection Engine.

No database implementation and no business rules exist in this package's
top level — abstract interface only.
"""

from app.repositories.signals.repository import BaseSignalDefinitionRepository

__all__ = ["BaseSignalDefinitionRepository"]
