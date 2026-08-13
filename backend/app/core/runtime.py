"""Central runtime shared by every MarketMind AI agent.

This module defines AgentRuntime, the dependency-injection container that
gives every agent access to shared services — logging, configuration, the
knowledge hub, memory, the tool registry, and the event bus — through
abstract interfaces only. AgentRuntime contains no business logic: it does
not implement, construct, or configure any concrete service. It is assembled
once, by application bootstrap code, and injected into agents.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.agents.base import MemoryInterface

__all__ = [
    "ConfigurationInterface",
    "KnowledgeHubInterface",
    "ToolRegistryInterface",
    "EventBusInterface",
    "AgentRuntime",
]


@runtime_checkable
class ConfigurationInterface(Protocol):
    """Abstract contract for reading application configuration values.

    Concrete configuration loading (environment variables, secrets, config
    files) is implemented elsewhere; AgentRuntime only depends on this shape.
    """

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value by key, or `default` if absent."""
        ...


@runtime_checkable
class KnowledgeHubInterface(Protocol):
    """Abstract contract for retrieving domain knowledge.

    Concrete knowledge retrieval (e.g. ChromaDB similarity search) is
    implemented in the `knowledge/` package; AgentRuntime only depends on
    this shape.
    """

    async def query(self, query: str, top_k: int = 5) -> list[Any]:
        """Retrieve up to `top_k` knowledge items relevant to `query`."""
        ...


@runtime_checkable
class ToolRegistryInterface(Protocol):
    """Abstract contract for resolving tools available to agents.

    Concrete tool registration and lookup is implemented in the `tools/`
    package; AgentRuntime only depends on this shape.
    """

    def get_tool(self, name: str) -> Any:
        """Resolve a registered tool by name."""
        ...

    def list_tools(self) -> tuple[str, ...]:
        """List the names of all currently registered tools."""
        ...


@runtime_checkable
class EventBusInterface(Protocol):
    """Abstract contract for publishing and subscribing to system events.

    Concrete event delivery (e.g. Redis pub/sub) is implemented elsewhere;
    AgentRuntime only depends on this shape.
    """

    async def publish(self, event_name: str, payload: Any) -> None:
        """Publish `payload` under `event_name` to all subscribers."""
        ...

    def subscribe(self, event_name: str, handler: Any) -> None:
        """Register `handler` to be invoked when `event_name` is published."""
        ...


class AgentRuntime:
    """Dependency-injection container of shared services for all agents.

    AgentRuntime is a composition root, not a service implementation: it
    holds references to six injected interfaces and exposes each through a
    read-only property. It never constructs, locates, or configures a
    concrete service itself — every dependency arrives fully formed via the
    constructor, supplied by whatever assembles the runtime at application
    startup (e.g. the FastAPI app's dependency wiring).

    Agents receive a single AgentRuntime instance and reach every shared
    service exclusively through it, rather than importing or instantiating
    services directly.
    """

    def __init__(
        self,
        logger: logging.Logger,
        configuration: ConfigurationInterface,
        knowledge_hub: KnowledgeHubInterface,
        memory: "MemoryInterface",
        tool_registry: ToolRegistryInterface,
        event_bus: EventBusInterface,
    ) -> None:
        """Assemble the runtime from its injected service dependencies.

        Args:
            logger: Structured logger shared across agents.
            configuration: Interface for reading application configuration.
            knowledge_hub: Interface for domain knowledge retrieval.
            memory: Interface for short-term and long-term memory access,
                as defined by `app.agents.base.MemoryInterface`.
            tool_registry: Interface for resolving agent-callable tools.
            event_bus: Interface for publishing and subscribing to system
                events.
        """
        self._logger = logger
        self._configuration = configuration
        self._knowledge_hub = knowledge_hub
        self._memory = memory
        self._tool_registry = tool_registry
        self._event_bus = event_bus

    @property
    def logger(self) -> logging.Logger:
        """Structured logger shared across agents."""
        return self._logger

    @property
    def configuration(self) -> ConfigurationInterface:
        """Interface for reading application configuration."""
        return self._configuration

    @property
    def knowledge_hub(self) -> KnowledgeHubInterface:
        """Interface for domain knowledge retrieval."""
        return self._knowledge_hub

    @property
    def memory(self) -> "MemoryInterface":
        """Interface for short-term and long-term memory access."""
        return self._memory

    @property
    def tool_registry(self) -> ToolRegistryInterface:
        """Interface for resolving agent-callable tools."""
        return self._tool_registry

    @property
    def event_bus(self) -> EventBusInterface:
        """Interface for publishing and subscribing to system events."""
        return self._event_bus
