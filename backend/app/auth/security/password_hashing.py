"""Password hashing abstraction.

`Pbkdf2PasswordHasher` is the one concrete implementation: PBKDF2-HMAC-
SHA256 via the standard library only (`hashlib.pbkdf2_hmac`,
`secrets.token_bytes` for the salt, `hmac.compare_digest` for a
constant-time comparison on verify) — no third-party dependency
(`bcrypt`/`argon2-cffi`/`passlib`) is introduced. This mirrors this
codebase's whole-project discipline of never adding a dependency beyond
what `pyproject.toml` already declares; PBKDF2-HMAC-SHA256 with a high
iteration count is a recognized, still-approved choice (OWASP's own
Password Storage Cheat Sheet lists it alongside bcrypt/scrypt/argon2)
when a project specifically wants to avoid a new native/compiled
dependency. `BasePasswordHasher` keeps this swappable — a future sprint
can add an `Argon2PasswordHasher` without changing any caller.

The hash string format is self-describing
(`pbkdf2_sha256$<iterations>$<salt_b64>$<derived_b64>`), the same
convention Django's own PBKDF2 hasher uses — it lets a future iteration-
count increase apply to newly-hashed passwords without invalidating
already-stored hashes (`verify()` reads the iteration count *from the
stored hash*, not from the currently-configured default).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from abc import ABC, abstractmethod

__all__ = ["BasePasswordHasher", "Pbkdf2PasswordHasher"]

_ALGORITHM_TAG = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 600_000
_SALT_BYTES = 16


class BasePasswordHasher(ABC):
    """Abstract base class every password hasher implementation must inherit."""

    @abstractmethod
    def hash(self, password: str) -> str:
        """Return a self-describing hash string for `password`. Never
        raises for a well-formed `str` input."""
        raise NotImplementedError

    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool:
        """Whether `password` matches `hashed`. Returns `False` (never
        raises) for a malformed or unrecognized `hashed` string."""
        raise NotImplementedError


class Pbkdf2PasswordHasher(BasePasswordHasher):
    def __init__(self, *, iterations: int = _DEFAULT_ITERATIONS) -> None:
        self._iterations = iterations

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(_SALT_BYTES)
        derived = self._derive(password, salt, self._iterations)
        return (
            f"{_ALGORITHM_TAG}${self._iterations}$"
            f"{base64.b64encode(salt).decode('ascii')}${base64.b64encode(derived).decode('ascii')}"
        )

    def verify(self, password: str, hashed: str) -> bool:
        parts = hashed.split("$")
        if len(parts) != 4:
            return False
        algorithm, iterations_str, salt_b64, derived_b64 = parts
        if algorithm != _ALGORITHM_TAG:
            return False
        try:
            iterations = int(iterations_str)
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(derived_b64)
        except (ValueError, TypeError):
            return False
        actual = self._derive(password, salt, iterations)
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def _derive(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
