"""Auth Repository: persistence contract for the Authentication &
Authorization Framework.

No business rules exist in this package's top level — abstract interface
only. See `postgres/` for the concrete implementation.
"""

from app.auth.repositories.repository import BaseAuthRepository

__all__ = ["BaseAuthRepository"]
