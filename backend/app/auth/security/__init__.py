"""Security primitives for the Authentication & Authorization Framework:
clock, password hashing, JWT signing, and secret loading — every one an
abstraction with exactly one stdlib-only concrete implementation."""

from app.auth.security.clock import BaseClock, SystemClock
from app.auth.security.jwt_signer import BaseJWTSigner, HmacJWTSigner
from app.auth.security.password_hashing import BasePasswordHasher, Pbkdf2PasswordHasher
from app.auth.security.secrets_loader import load_jwt_secret

__all__ = [
    "BaseClock",
    "SystemClock",
    "BasePasswordHasher",
    "Pbkdf2PasswordHasher",
    "BaseJWTSigner",
    "HmacJWTSigner",
    "load_jwt_secret",
]
