"""Tests for the password hashing abstraction."""

from __future__ import annotations

from app.auth.security.password_hashing import Pbkdf2PasswordHasher


def _hasher() -> Pbkdf2PasswordHasher:
    return Pbkdf2PasswordHasher(iterations=1000)  # low iteration count -> fast tests


def test_hash_then_verify_round_trips() -> None:
    hasher = _hasher()
    hashed = hasher.hash("correct horse battery staple")
    assert hasher.verify("correct horse battery staple", hashed) is True


def test_verify_rejects_wrong_password() -> None:
    hasher = _hasher()
    hashed = hasher.hash("correct horse battery staple")
    assert hasher.verify("wrong password", hashed) is False


def test_hash_output_is_self_describing() -> None:
    hasher = _hasher()
    hashed = hasher.hash("password123")
    parts = hashed.split("$")
    assert len(parts) == 4
    assert parts[0] == "pbkdf2_sha256"
    assert parts[1] == "1000"


def test_hash_is_salted_differently_each_time() -> None:
    hasher = _hasher()
    first = hasher.hash("same-password")
    second = hasher.hash("same-password")
    assert first != second
    assert hasher.verify("same-password", first)
    assert hasher.verify("same-password", second)


def test_verify_rejects_malformed_hash_string() -> None:
    hasher = _hasher()
    assert hasher.verify("anything", "not-a-valid-hash") is False
    assert hasher.verify("anything", "too$few$parts") is False
    assert hasher.verify("anything", "wrong_algo$1000$c2FsdA==$ZGVyaXZlZA==") is False


def test_verify_rejects_non_numeric_iterations() -> None:
    hasher = _hasher()
    assert hasher.verify("anything", "pbkdf2_sha256$not-a-number$c2FsdA==$ZGVyaXZlZA==") is False


def test_verify_respects_the_iteration_count_stored_in_the_hash() -> None:
    """A hash produced with a different iteration count than the
    hasher's own default must still verify correctly — `verify()` reads
    the count from the hash, never from `self._iterations`."""
    low_iteration_hasher = Pbkdf2PasswordHasher(iterations=500)
    high_iteration_hasher = Pbkdf2PasswordHasher(iterations=2000)
    hashed = low_iteration_hasher.hash("password123")

    assert high_iteration_hasher.verify("password123", hashed) is True
