"""Shared fixtures and factories for MemoryService tests.

Only the production MemoryService is exercised anywhere in this package —
no Redis, PostgreSQL, ChromaDB, filesystem, network, LLM, or KnowledgeHub
involvement.
"""

from __future__ import annotations

import logging

import pytest

from app.bootstrap import (
    AppSettings,
    EmptyKnowledgeHub,
    EmptyToolRegistry,
    NoOpEventBus,
    SettingsConfiguration,
)
from app.core.runtime import AgentRuntime
from app.memory import MemoryEntry, MemoryScope, MemoryService

_LOGGER = logging.getLogger("test.memory")


@pytest.fixture
def service() -> MemoryService:
    """A fresh MemoryService (in-process, no shared state between tests)."""
    return MemoryService()


def build_agent_runtime(memory: MemoryService) -> AgentRuntime:
    """An AgentRuntime wired with `memory` and otherwise-inert defaults,
    for exercising Memory Service injection without any real dependency."""
    return AgentRuntime(
        logger=_LOGGER,
        configuration=SettingsConfiguration(AppSettings()),
        knowledge_hub=EmptyKnowledgeHub(),
        memory=memory,
        tool_registry=EmptyToolRegistry(),
        event_bus=NoOpEventBus(),
    )


def workflow_entry(
    key: str = "k", value: object = 1, scope_id: str = "wf-1", **overrides: object
) -> MemoryEntry:
    return MemoryEntry(key=key, value=value, scope=MemoryScope.WORKFLOW, scope_id=scope_id, **overrides)


def conversation_entry(
    key: str = "k", value: object = 1, scope_id: str = "conv-1", **overrides: object
) -> MemoryEntry:
    return MemoryEntry(
        key=key, value=value, scope=MemoryScope.CONVERSATION, scope_id=scope_id, **overrides
    )


def user_entry(
    key: str = "k", value: object = 1, scope_id: str = "user-1", **overrides: object
) -> MemoryEntry:
    return MemoryEntry(key=key, value=value, scope=MemoryScope.USER, scope_id=scope_id, **overrides)


def agent_entry(
    key: str = "k", value: object = 1, scope_id: str = "AGT-001", **overrides: object
) -> MemoryEntry:
    return MemoryEntry(key=key, value=value, scope=MemoryScope.AGENT, scope_id=scope_id, **overrides)


def global_entry(key: str = "k", value: object = 1, **overrides: object) -> MemoryEntry:
    return MemoryEntry(key=key, value=value, scope=MemoryScope.GLOBAL, **overrides)
