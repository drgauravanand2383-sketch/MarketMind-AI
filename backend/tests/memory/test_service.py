"""Tests for MemoryService (app.memory.service) — the production Memory Service.

Only MemoryService itself is exercised. No Redis, PostgreSQL, ChromaDB,
filesystem, network, LLM, or KnowledgeHub involvement anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.agents.base import MemoryInterface
from app.memory import (
    MemoryEntry,
    MemoryQuery,
    MemoryScope,
    MemoryService,
    MemoryTerm,
)
from tests.memory.conftest import (
    agent_entry,
    build_agent_runtime,
    conversation_entry,
    global_entry,
    user_entry,
    workflow_entry,
)

# --- Storing entries -----------------------------------------------------------


async def test_store_returns_the_stored_entry(service: MemoryService) -> None:
    stored = await service.store(global_entry(key="k", value=42))
    assert stored.value == 42


async def test_stored_entry_is_persisted_in_process(service: MemoryService) -> None:
    await service.store(global_entry(key="k", value="v"))

    result = await service.retrieve(MemoryQuery(scope=MemoryScope.GLOBAL, key="k"))

    assert result.count == 1
    assert result.entries[0].value == "v"


# --- Retrieving entries -----------------------------------------------------------


async def test_retrieve_by_key_returns_empty_result_when_absent(service: MemoryService) -> None:
    result = await service.retrieve(MemoryQuery(scope=MemoryScope.GLOBAL, key="missing"))
    assert result.entries == []
    assert result.count == 0


async def test_retrieve_without_key_returns_every_entry_in_scope(service: MemoryService) -> None:
    await service.store(workflow_entry(key="a", scope_id="wf-1"))
    await service.store(workflow_entry(key="b", scope_id="wf-1"))
    await service.store(workflow_entry(key="c", scope_id="wf-2"))

    result = await service.retrieve(MemoryQuery(scope=MemoryScope.WORKFLOW, scope_id="wf-1"))

    assert {entry.key for entry in result.entries} == {"a", "b"}


# --- Overwriting an existing key -----------------------------------------------------------


async def test_overwrite_replaces_the_value(service: MemoryService) -> None:
    await service.store(global_entry(key="k", value="first"))
    await service.store(global_entry(key="k", value="second"))

    result = await service.retrieve(MemoryQuery(scope=MemoryScope.GLOBAL, key="k"))
    assert result.entries[0].value == "second"


async def test_overwrite_preserves_original_created_at(service: MemoryService) -> None:
    first = await service.store(global_entry(key="k", value="first"))
    second = await service.store(global_entry(key="k", value="second"))

    assert second.created_at == first.created_at


async def test_overwrite_updates_updated_at(service: MemoryService) -> None:
    stale_time = datetime.now(UTC) - timedelta(hours=1)
    await service.store(
        global_entry(key="k", value="first", created_at=stale_time, updated_at=stale_time)
    )

    second = await service.store(global_entry(key="k", value="second"))

    assert second.updated_at > stale_time


# --- Deleting entries -----------------------------------------------------------


async def test_delete_removes_the_entry(service: MemoryService) -> None:
    await service.store(global_entry(key="k", value=1))

    deleted = await service.delete(MemoryScope.GLOBAL, "k")

    assert deleted is True
    result = await service.retrieve(MemoryQuery(scope=MemoryScope.GLOBAL, key="k"))
    assert result.entries == []


async def test_delete_returns_false_when_absent(service: MemoryService) -> None:
    assert await service.delete(MemoryScope.GLOBAL, "does-not-exist") is False


async def test_delete_is_scoped_to_scope_id(service: MemoryService) -> None:
    await service.store(user_entry(key="k", scope_id="user-1"))

    deleted = await service.delete(MemoryScope.USER, "k", scope_id="user-2")

    assert deleted is False
    result = await service.retrieve(MemoryQuery(scope=MemoryScope.USER, scope_id="user-1", key="k"))
    assert result.count == 1


# --- Clearing a scope -----------------------------------------------------------


async def test_clear_scope_removes_only_that_scope_id(service: MemoryService) -> None:
    await service.store(conversation_entry(key="a", scope_id="conv-1"))
    await service.store(conversation_entry(key="b", scope_id="conv-1"))
    await service.store(conversation_entry(key="c", scope_id="conv-2"))

    removed = await service.clear_scope(MemoryScope.CONVERSATION, scope_id="conv-1")

    assert removed == 2
    remaining = await service.retrieve(MemoryQuery(scope=MemoryScope.CONVERSATION, scope_id="conv-2"))
    assert remaining.count == 1


async def test_clear_scope_returns_zero_when_nothing_to_clear(service: MemoryService) -> None:
    assert await service.clear_scope(MemoryScope.GLOBAL) == 0


# --- Workflow-scoped memory -----------------------------------------------------------


async def test_workflow_memory_round_trip(service: MemoryService) -> None:
    await service.store(workflow_entry(key="stage", value="collected", scope_id="wf-1"))
    result = await service.retrieve(MemoryQuery(scope=MemoryScope.WORKFLOW, scope_id="wf-1", key="stage"))
    assert result.entries[0].value == "collected"


async def test_workflow_memory_isolated_by_scope_id(service: MemoryService) -> None:
    await service.store(workflow_entry(key="k", value="wf-1-value", scope_id="wf-1"))
    await service.store(workflow_entry(key="k", value="wf-2-value", scope_id="wf-2"))

    result_1 = await service.retrieve(MemoryQuery(scope=MemoryScope.WORKFLOW, scope_id="wf-1", key="k"))
    result_2 = await service.retrieve(MemoryQuery(scope=MemoryScope.WORKFLOW, scope_id="wf-2", key="k"))

    assert result_1.entries[0].value == "wf-1-value"
    assert result_2.entries[0].value == "wf-2-value"


# --- Conversation-scoped memory -----------------------------------------------------------


async def test_conversation_memory_round_trip(service: MemoryService) -> None:
    await service.store(conversation_entry(key="last_message", value="hi", scope_id="conv-1"))
    result = await service.retrieve(
        MemoryQuery(scope=MemoryScope.CONVERSATION, scope_id="conv-1", key="last_message")
    )
    assert result.entries[0].value == "hi"


# --- User-scoped memory -----------------------------------------------------------


async def test_user_memory_round_trip(service: MemoryService) -> None:
    await service.store(user_entry(key="preference", value="dark_mode", scope_id="user-1"))
    result = await service.retrieve(
        MemoryQuery(scope=MemoryScope.USER, scope_id="user-1", key="preference")
    )
    assert result.entries[0].value == "dark_mode"


# --- Agent-scoped memory -----------------------------------------------------------


async def test_agent_memory_round_trip(service: MemoryService) -> None:
    await service.store(agent_entry(key="last_run", value="ok", scope_id="AGT-003"))
    result = await service.retrieve(
        MemoryQuery(scope=MemoryScope.AGENT, scope_id="AGT-003", key="last_run")
    )
    assert result.entries[0].value == "ok"


# --- Global-scoped memory -----------------------------------------------------------


async def test_global_memory_round_trip(service: MemoryService) -> None:
    await service.store(global_entry(key="feature_flag", value=True))
    result = await service.retrieve(MemoryQuery(scope=MemoryScope.GLOBAL, key="feature_flag"))
    assert result.entries[0].value is True


async def test_all_five_scopes_are_isolated_from_each_other(service: MemoryService) -> None:
    """The same key under every different scope never collides."""
    await service.store(workflow_entry(key="k", value="workflow", scope_id="1"))
    await service.store(conversation_entry(key="k", value="conversation", scope_id="1"))
    await service.store(user_entry(key="k", value="user", scope_id="1"))
    await service.store(agent_entry(key="k", value="agent", scope_id="1"))
    await service.store(global_entry(key="k", value="global"))

    status = await service.health_check()

    assert status.entry_count == 5
    assert all(count == 1 for count in status.scope_counts.values())


# --- MemoryQuery filtering -----------------------------------------------------------


async def test_query_filters_by_term(service: MemoryService) -> None:
    await service.store(agent_entry(key="a", term=MemoryTerm.SHORT_TERM))
    await service.store(agent_entry(key="b", term=MemoryTerm.LONG_TERM))

    result = await service.retrieve(
        MemoryQuery(scope=MemoryScope.AGENT, scope_id="AGT-001", term=MemoryTerm.LONG_TERM)
    )

    assert [entry.key for entry in result.entries] == ["b"]


async def test_query_without_term_returns_entries_of_every_term(service: MemoryService) -> None:
    await service.store(agent_entry(key="a", term=MemoryTerm.SHORT_TERM))
    await service.store(agent_entry(key="b", term=MemoryTerm.LONG_TERM))

    result = await service.retrieve(MemoryQuery(scope=MemoryScope.AGENT, scope_id="AGT-001"))

    assert {entry.key for entry in result.entries} == {"a", "b"}


async def test_query_by_key_and_term_that_does_not_match_returns_empty(service: MemoryService) -> None:
    await service.store(agent_entry(key="a", term=MemoryTerm.SHORT_TERM))

    result = await service.retrieve(
        MemoryQuery(scope=MemoryScope.AGENT, scope_id="AGT-001", key="a", term=MemoryTerm.LONG_TERM)
    )

    assert result.entries == []


# --- Duplicate overwrite behavior -----------------------------------------------------------


async def test_repeated_stores_at_the_same_address_do_not_accumulate_duplicates(
    service: MemoryService,
) -> None:
    """store() overwrites in place — retrieving that scope never returns
    more than one entry per (scope, scope_id, key), regardless of how many
    times it was written."""
    for value in range(5):
        await service.store(global_entry(key="k", value=value))

    result = await service.retrieve(MemoryQuery(scope=MemoryScope.GLOBAL))

    assert len(result.entries) == 1
    assert result.entries[0].value == 4


async def test_overwrite_at_one_key_does_not_affect_a_different_key_in_the_same_scope(
    service: MemoryService,
) -> None:
    await service.store(global_entry(key="a", value=1))
    await service.store(global_entry(key="b", value=2))

    await service.store(global_entry(key="a", value="overwritten"))

    result = await service.retrieve(MemoryQuery(scope=MemoryScope.GLOBAL))
    assert {entry.key: entry.value for entry in result.entries} == {"a": "overwritten", "b": 2}


# --- health_check() -----------------------------------------------------------


async def test_health_check_on_empty_service(service: MemoryService) -> None:
    status = await service.health_check()
    assert status.healthy is True
    assert status.entry_count == 0
    assert all(count == 0 for count in status.scope_counts.values())


async def test_health_check_reports_every_scope_key(service: MemoryService) -> None:
    status = await service.health_check()
    assert set(status.scope_counts.keys()) == set(MemoryScope)


async def test_health_check_does_not_mutate_storage(service: MemoryService) -> None:
    await service.store(global_entry(key="k", value=1))

    await service.health_check()
    await service.health_check()

    status = await service.health_check()
    assert status.entry_count == 1


# --- Validation rules -----------------------------------------------------------


@pytest.mark.parametrize(
    "scope", [MemoryScope.WORKFLOW, MemoryScope.CONVERSATION, MemoryScope.USER, MemoryScope.AGENT]
)
def test_non_global_scope_requires_scope_id(scope: MemoryScope) -> None:
    with pytest.raises(ValidationError):
        MemoryEntry(key="k", value=1, scope=scope, scope_id=None)


def test_global_scope_forbids_scope_id() -> None:
    with pytest.raises(ValidationError):
        MemoryEntry(key="k", value=1, scope=MemoryScope.GLOBAL, scope_id="should-not-be-set")


def test_query_scope_validation_matches_entry_scope_validation() -> None:
    with pytest.raises(ValidationError):
        MemoryQuery(scope=MemoryScope.WORKFLOW, scope_id=None)
    with pytest.raises(ValidationError):
        MemoryQuery(scope=MemoryScope.GLOBAL, scope_id="should-not-be-set")


def test_entry_updated_at_before_created_at_raises() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        MemoryEntry(
            key="k",
            value=1,
            scope=MemoryScope.GLOBAL,
            created_at=now,
            updated_at=now - timedelta(seconds=1),
        )


def test_entry_key_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        MemoryEntry(key="", value=1, scope=MemoryScope.GLOBAL)


def test_entry_is_frozen_identifiers_are_immutable() -> None:
    entry = global_entry(key="k")
    with pytest.raises(ValidationError):
        entry.key = "changed"


def test_entry_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MemoryEntry(key="k", value=1, scope=MemoryScope.GLOBAL, unexpected_field="x")


async def test_storing_an_invalid_entry_is_impossible_by_construction(service: MemoryService) -> None:
    """MemoryService.store() takes an already-validated MemoryEntry, so an
    invalid one can never reach storage — construction itself raises."""
    with pytest.raises(ValidationError):
        entry = MemoryEntry(key="k", value=1, scope=MemoryScope.WORKFLOW, scope_id=None)
        await service.store(entry)


# --- AgentRuntime dependency injection -----------------------------------------------------------


def test_memory_service_satisfies_memory_interface(service: MemoryService) -> None:
    """MemoryService correctly implements the existing MemoryInterface."""
    assert isinstance(service, MemoryInterface)


def test_memory_service_injects_into_agent_runtime(service: MemoryService) -> None:
    runtime = build_agent_runtime(service)
    assert runtime.memory is service


async def test_agent_runtime_memory_is_usable_through_the_interface(service: MemoryService) -> None:
    runtime = build_agent_runtime(service)

    await runtime.memory.write("k", "v")

    assert await runtime.memory.read("k") == "v"


async def test_agent_runtime_memory_write_operates_on_global_scope(service: MemoryService) -> None:
    """write() (MemoryInterface) and store()/retrieve() (MemoryService's
    own API) observe the same underlying storage."""
    runtime = build_agent_runtime(service)

    await runtime.memory.write("k", "v")

    result = await service.retrieve(MemoryQuery(scope=MemoryScope.GLOBAL, key="k"))
    assert result.entries[0].value == "v"
