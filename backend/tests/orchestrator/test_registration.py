"""Tests for AgentOrchestrator's agent registration."""

from __future__ import annotations

import pytest

from app.orchestrator.exceptions import AgentAlreadyRegisteredError, AgentNotRegisteredError
from app.orchestrator.orchestrator import AgentOrchestrator
from tests.orchestrator.conftest import FakeAgent, TaskInput


def test_register_agent_appears_in_list_agents() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))

    assert orchestrator.list_agents() == ("a",)


def test_list_agents_returns_sorted_ids() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("zeta", FakeAgent(agent_id="zeta"))
    orchestrator.register_agent("alpha", FakeAgent(agent_id="alpha"))

    assert orchestrator.list_agents() == ("alpha", "zeta")


def test_list_agents_empty_when_nothing_registered() -> None:
    orchestrator = AgentOrchestrator()
    assert orchestrator.list_agents() == ()


def test_constructor_accepts_an_initial_mapping_of_agents() -> None:
    orchestrator = AgentOrchestrator({"a": FakeAgent(agent_id="a"), "b": FakeAgent(agent_id="b")})
    assert orchestrator.list_agents() == ("a", "b")


# --- Duplicate registration -----------------------------------------------------------


def test_duplicate_registration_raises() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))

    with pytest.raises(AgentAlreadyRegisteredError):
        orchestrator.register_agent("a", FakeAgent(agent_id="a"))


def test_duplicate_registration_does_not_replace_existing_agent() -> None:
    orchestrator = AgentOrchestrator()
    first = FakeAgent(agent_id="a", multiplier=1)
    orchestrator.register_agent("a", first)

    try:
        orchestrator.register_agent("a", FakeAgent(agent_id="a", multiplier=99))
    except AgentAlreadyRegisteredError:
        pass

    assert orchestrator._agents["a"] is first


# --- Unregister -----------------------------------------------------------


def test_unregister_removes_agent() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))

    orchestrator.unregister_agent("a")

    assert orchestrator.list_agents() == ()


def test_unregister_unknown_id_is_a_no_op() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.unregister_agent("does-not-exist")  # must not raise
    assert orchestrator.list_agents() == ()


# --- Unknown agent -----------------------------------------------------------


async def test_execute_one_unknown_agent_raises() -> None:
    orchestrator = AgentOrchestrator()

    with pytest.raises(AgentNotRegisteredError):
        await orchestrator.execute_one("does-not-exist", TaskInput(value=1))


async def test_unregistered_agent_can_no_longer_be_executed_directly() -> None:
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent("a", FakeAgent(agent_id="a"))
    orchestrator.unregister_agent("a")

    with pytest.raises(AgentNotRegisteredError):
        await orchestrator.execute_one("a", TaskInput(value=1))
