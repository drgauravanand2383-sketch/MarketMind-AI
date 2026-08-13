"""Tests for the JWT signing abstraction — encode/decode round-trips and
every security-sensitive rejection path (tampering, wrong secret,
algorithm confusion, malformed segments)."""

from __future__ import annotations

import base64
import json

import pytest

from app.auth.exceptions import TokenInvalidError, TokenMalformedError
from app.auth.security.jwt_signer import HmacJWTSigner


def _signer(secret: str = "test-secret-key") -> HmacJWTSigner:
    return HmacJWTSigner(secret)


# --- round trip -----------------------------------------------------------


def test_encode_then_decode_round_trips_claims() -> None:
    signer = _signer()
    claims = {"sub": "user1", "exp": 9999999999, "roles": ["ADMIN"]}

    token = signer.encode(claims)
    decoded = signer.decode(token)

    assert decoded == claims


def test_encoded_token_has_three_dot_separated_segments() -> None:
    signer = _signer()
    token = signer.encode({"sub": "user1"})

    assert len(token.split(".")) == 3


def test_encoded_token_header_declares_hs256() -> None:
    signer = _signer()
    token = signer.encode({"sub": "user1"})
    header_b64 = token.split(".")[0]
    padding = "=" * (-len(header_b64) % 4)
    header = json.loads(base64.urlsafe_b64decode(header_b64 + padding))

    assert header == {"alg": "HS256", "typ": "JWT"}


def test_encode_is_deterministic_for_identical_claims() -> None:
    signer = _signer()
    claims = {"sub": "user1", "exp": 123}

    assert signer.encode(claims) == signer.encode(claims)


# --- construction -----------------------------------------------------------


def test_rejects_unsupported_algorithm() -> None:
    with pytest.raises(ValueError):
        HmacJWTSigner("secret", algorithm="RS256")


def test_rejects_empty_secret() -> None:
    with pytest.raises(ValueError):
        HmacJWTSigner("")


# --- tamper detection -----------------------------------------------------------


def test_tampered_payload_is_rejected() -> None:
    signer = _signer()
    token = signer.encode({"sub": "user1", "admin": False})
    header_b64, payload_b64, signature_b64 = token.split(".")

    forged_payload = base64.urlsafe_b64encode(json.dumps({"sub": "user1", "admin": True}).encode()).rstrip(b"=").decode()
    forged_token = f"{header_b64}.{forged_payload}.{signature_b64}"

    with pytest.raises((TokenInvalidError, TokenMalformedError)):
        signer.decode(forged_token)


def test_tampered_signature_is_rejected() -> None:
    signer = _signer()
    token = signer.encode({"sub": "user1"})
    header_b64, payload_b64, signature_b64 = token.split(".")
    corrupted_signature = ("A" if signature_b64[0] != "A" else "B") + signature_b64[1:]

    with pytest.raises(TokenInvalidError):
        signer.decode(f"{header_b64}.{payload_b64}.{corrupted_signature}")


def test_token_signed_with_a_different_secret_is_rejected() -> None:
    signer_a = _signer("secret-a")
    signer_b = _signer("secret-b")
    token = signer_a.encode({"sub": "user1"})

    with pytest.raises(TokenInvalidError):
        signer_b.decode(token)


def test_signature_verification_uses_constant_time_comparison() -> None:
    """Not directly testable via timing in a unit test — this asserts
    the implementation detail instead: `hmac.compare_digest` is used,
    not `==`, by inspecting the source (a lightweight regression guard
    against a future refactor silently swapping it out)."""
    import inspect

    from app.auth.security import jwt_signer

    source = inspect.getsource(jwt_signer)
    assert "hmac.compare_digest" in source
    assert "signature == expected_signature" not in source


# --- algorithm confusion / alg:none -----------------------------------------------------------


def test_alg_none_header_is_rejected() -> None:
    signer = _signer()
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "attacker"}).encode()).rstrip(b"=").decode()
    forged_token = f"{header}.{payload}."

    with pytest.raises(TokenMalformedError):
        signer.decode(forged_token)


def test_mismatched_algorithm_header_is_rejected() -> None:
    signer = _signer()
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS512", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "user1"}).encode()).rstrip(b"=").decode()

    with pytest.raises(TokenMalformedError):
        signer.decode(f"{header}.{payload}.forged-signature")


# --- malformed tokens -----------------------------------------------------------


def test_rejects_token_with_too_few_segments() -> None:
    signer = _signer()
    with pytest.raises(TokenMalformedError):
        signer.decode("only.two")


def test_rejects_token_with_too_many_segments() -> None:
    signer = _signer()
    with pytest.raises(TokenMalformedError):
        signer.decode("a.b.c.d")


def test_rejects_non_base64_segments() -> None:
    signer = _signer()
    with pytest.raises(TokenMalformedError):
        signer.decode("not!!valid.base64!!.here!!")


def test_rejects_valid_base64_that_is_not_json() -> None:
    signer = _signer()
    not_json_b64 = base64.urlsafe_b64encode(b"not-json-content").rstrip(b"=").decode()
    with pytest.raises(TokenMalformedError):
        signer.decode(f"{not_json_b64}.{not_json_b64}.{not_json_b64}")


def test_rejects_completely_empty_string() -> None:
    signer = _signer()
    with pytest.raises(TokenMalformedError):
        signer.decode("")


def test_rejects_header_or_payload_that_is_not_a_json_object() -> None:
    signer = _signer()
    array_b64 = base64.urlsafe_b64encode(b"[1,2,3]").rstrip(b"=").decode()
    with pytest.raises(TokenMalformedError):
        signer.decode(f"{array_b64}.{array_b64}.sig")


def test_never_includes_the_secret_in_an_exception_message() -> None:
    signer = _signer("super-secret-value-12345")
    try:
        signer.decode("garbage.token.here")
    except TokenMalformedError as exc:
        assert "super-secret-value-12345" not in str(exc)
