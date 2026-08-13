"""Authentication providers: the provider-agnostic `AuthenticationProvider`
abstract contract, and its first concrete implementation, `JwtAuthenticationProvider`."""

from app.auth.providers.jwt import JwtAuthenticationProvider
from app.auth.providers.provider import AuthenticationProvider

__all__ = ["AuthenticationProvider", "JwtAuthenticationProvider"]
