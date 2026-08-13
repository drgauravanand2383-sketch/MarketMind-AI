"""JWT signing abstraction.

`HmacJWTSigner` is the one concrete implementation: HS256 (HMAC-SHA256),
implemented against the standard library only (`hmac`, `hashlib`,
`base64`, `json`) — no third-party JWT library (`pyjwt`/`python-jose`) is
introduced, the same no-new-dependency discipline
`app.auth.security.password_hashing` documents. The JWS Compact
Serialization format (RFC 7515) for HS256 is simple and fully specified —
`base64url(header) + "." + base64url(payload) + "." +
base64url(HMAC-SHA256(base64url(header) + "." + base64url(payload), secret))`
— straightforward to implement correctly without a library, provided the
security-sensitive details below are handled deliberately:

- Signature comparison uses `hmac.compare_digest` (constant-time) — never
  `==`, which would leak timing information about how many leading bytes
  matched.
- The decoded header's `alg` is checked against the *configured*
  algorithm and rejected otherwise — this signer never honors whatever
  algorithm a token's own header claims (the classic "alg confusion" /
  "alg: none" attack class), and supports exactly one algorithm (HS256);
  there is no code path that skips verification.
- Every parsing failure (wrong segment count, invalid base64url, invalid
  JSON) raises `TokenMalformedError`, distinct from a verified-but-invalid
  signature (`TokenInvalidError`) — callers (and tests) can tell "this
  isn't a JWT at all" apart from "this claims to be a JWT signed with the
  wrong key."
- The secret is held only as `bytes` in memory for the lifetime of this
  object; it is never logged, never included in an exception message, and
  this class has no `__repr__`/`__str__` override that could accidentally
  expose it (the default object repr does not include instance attributes).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from typing import Any

from app.auth.exceptions import TokenInvalidError, TokenMalformedError

__all__ = ["BaseJWTSigner", "HmacJWTSigner"]

_SUPPORTED_ALGORITHM = "HS256"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


class BaseJWTSigner(ABC):
    """Abstract base class every JWT signer implementation must inherit."""

    @abstractmethod
    def encode(self, claims: dict[str, Any]) -> str:
        """Serialize and sign `claims` into a compact JWT string."""
        raise NotImplementedError

    @abstractmethod
    def decode(self, token: str) -> dict[str, Any]:
        """Verify `token`'s signature and return its claims.

        Raises:
            TokenMalformedError: `token` is not well-formed JWS Compact
                Serialization, or its header names an unsupported algorithm.
            TokenInvalidError: `token` is well-formed but its signature
                does not verify.
        """
        raise NotImplementedError


class HmacJWTSigner(BaseJWTSigner):
    def __init__(self, secret: str, *, algorithm: str = _SUPPORTED_ALGORITHM) -> None:
        if algorithm != _SUPPORTED_ALGORITHM:
            raise ValueError(f"HmacJWTSigner only supports {_SUPPORTED_ALGORITHM!r}, got {algorithm!r}.")
        if not secret:
            raise ValueError("secret must not be empty.")
        self._secret = secret.encode("utf-8")
        self._algorithm = algorithm

    def encode(self, claims: dict[str, Any]) -> str:
        header = {"alg": self._algorithm, "typ": "JWT"}
        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
        signature_b64 = _b64url_encode(self._sign(header_b64, payload_b64))
        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def decode(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise TokenMalformedError(f"expected 3 segments, got {len(parts)}.")
        header_b64, payload_b64, signature_b64 = parts

        try:
            header = json.loads(_b64url_decode(header_b64))
            payload = json.loads(_b64url_decode(payload_b64))
            signature = _b64url_decode(signature_b64)
        except (ValueError, binascii.Error) as exc:
            raise TokenMalformedError(f"could not decode segments: {exc}") from exc

        if not isinstance(header, dict) or not isinstance(payload, dict):
            raise TokenMalformedError("header and payload must both be JSON objects.")
        if header.get("alg") != self._algorithm:
            raise TokenMalformedError(f"unsupported algorithm {header.get('alg')!r}.")

        expected_signature = self._sign(header_b64, payload_b64)
        if not hmac.compare_digest(signature, expected_signature):
            raise TokenInvalidError()

        return payload

    def _sign(self, header_b64: str, payload_b64: str) -> bytes:
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        return hmac.new(self._secret, signing_input, hashlib.sha256).digest()
