"""Tests for PolicyEvaluator."""

from __future__ import annotations

import pytest

from app.auth.exceptions import AuthorizationDeniedError
from app.auth.models.authentication import AuthenticatedPrincipal
from app.auth.policies.evaluator import PolicyEvaluator
from app.auth.policies.policy import RequireRole


def _principal(roles: tuple[str, ...] = ()) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id="u1", username="alice", roles=roles, token_id="t1")


def test_evaluate_returns_true_when_satisfied() -> None:
    evaluator = PolicyEvaluator()
    assert evaluator.evaluate(RequireRole("ADMIN"), _principal(roles=("ADMIN",))) is True


def test_evaluate_returns_false_when_not_satisfied() -> None:
    evaluator = PolicyEvaluator()
    assert evaluator.evaluate(RequireRole("ADMIN"), _principal()) is False


def test_check_does_not_raise_when_satisfied() -> None:
    evaluator = PolicyEvaluator()
    evaluator.check(RequireRole("ADMIN"), _principal(roles=("ADMIN",)))  # must not raise


def test_check_raises_authorization_denied_when_not_satisfied() -> None:
    evaluator = PolicyEvaluator()
    with pytest.raises(AuthorizationDeniedError) as exc_info:
        evaluator.check(RequireRole("ADMIN"), _principal())
    assert "RequireRole" in str(exc_info.value)
