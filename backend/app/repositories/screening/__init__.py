"""Screening Repository: persistence contract for the Screening Engine.

No database implementation and no business rules exist in this package's
top level — abstract interface only.
"""

from app.repositories.screening.repository import BaseScreeningRepository

__all__ = ["BaseScreeningRepository"]
