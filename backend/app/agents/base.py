"""Abstract contract every MarketMind AI agent must implement.

This module defines the BaseAgent interface, its lifecycle hooks, its
structured-logging behavior, and the memory-access boundary shared by all
agents. It contains no business logic and no knowledge of any specific
agent's responsibility — those are supplied entirely by concrete subclasses
under `app/agents/`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.core.context import ExecutionContext

__all__ = ["AgentLayer", "MemoryInterface", "BaseAgent"]


class AgentLayer(str, Enum):
    """Architectural layers an agent may belong to.

    Values correspond to the approved multi-agent layer design: every agent
    must declare exactly one layer via its `layer` property.
    """

    ORCHESTRATION = "orchestration"
    INGESTION = "ingestion"
    REASONING = "reasoning"
    MEMORY = "memory"
    VALIDATION = "validation"
    INTEGRATION = "integration"
    SECURITY_PRIVACY = "security_privacy"
    PRESENTATION = "presentation"


@runtime_checkable
class MemoryInterface(Protocol):
    """Abstract contract for memory access.

    BaseAgent and its subclasses may only reach memory through an object
    satisfying this interface. Concrete storage backends (PostgreSQL, Redis,
    ChromaDB) are implemented elsewhere and injected at construction time;
    BaseAgent never imports or calls a storage client directly.
    """

    async def read(self, key: str) -> Any:
        """Retrieve a value from memory by key."""
        ...

    async def write(self, key: str, value: Any) -> None:
        """Persist a value to memory under a key."""
        ...


class BaseAgent(ABC):
    """Abstract base class every MarketMind AI agent must inherit.

    BaseAgent defines the invocation contract, lifecycle hooks, structured
    logging behavior, and memory access boundary shared by all agents. Each
    concrete agent (e.g. AGT-001 Orchestrator, AGT-009 Sentiment Analyst)
    implements the abstract members below; BaseAgent itself performs no
    domain work.
    """

    def __init__(self, memory: MemoryInterface) -> None:
        """Initialize the agent with its injected memory dependency.

        Args:
            memory: An object satisfying `MemoryInterface`, injected by the
                Orchestrator. BaseAgent never constructs or looks up its own
                memory dependency, in keeping with the Dependency Inversion
                Principle.
        """
        self._memory = memory
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} agent_id={self.agent_id!r} layer={self.layer!r}>"

    # ------------------------------------------------------------------
    # Controlled access to injected dependencies
    # ------------------------------------------------------------------

    @property
    def memory(self) -> MemoryInterface:
        """The injected memory interface this agent is permitted to use."""
        return self._memory

    @property
    def logger(self) -> logging.Logger:
        """The structured logger scoped to this agent's class name."""
        return self._logger

    # ------------------------------------------------------------------
    # Identity & metadata contract
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """The agent's approved identifier (e.g. 'AGT-001'). Immutable."""
        raise NotImplementedError

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """The agent's approved name (e.g. 'Orchestrator'). Immutable."""
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """The agent specification version this implementation satisfies."""
        raise NotImplementedError

    @property
    @abstractmethod
    def layer(self) -> AgentLayer:
        """The architectural layer this agent belongs to."""
        raise NotImplementedError

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[str]:
        """The declared, immutable set of capabilities this agent provides."""
        raise NotImplementedError

    @property
    @abstractmethod
    def input_schema(self) -> type[BaseModel]:
        """The Pydantic model class defining this agent's expected input shape."""
        raise NotImplementedError

    @property
    @abstractmethod
    def output_schema(self) -> type[BaseModel]:
        """The Pydantic model class defining this agent's produced output shape."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Abstract execution contract
    # ------------------------------------------------------------------

    @abstractmethod
    async def run(self, context: ExecutionContext, input_data: BaseModel) -> BaseModel:
        """Execute the agent's single responsibility.

        Args:
            context: The shared Execution Context for the current workflow run.
            input_data: Input conforming to `input_schema`.

        Returns:
            Output conforming to `output_schema`.
        """
        raise NotImplementedError

    @abstractmethod
    async def validate_input(self, input_data: BaseModel) -> bool:
        """Validate `input_data` against this agent's semantic input rules.

        Called before `run`. Schema-shape validation is handled by
        `input_schema` itself; this method covers agent-specific rules
        beyond shape (e.g. permitted ranges, required combinations).
        """
        raise NotImplementedError

    @abstractmethod
    async def validate_output(self, output_data: BaseModel) -> bool:
        """Validate `output_data` against this agent's semantic output rules.

        Called after `run`, before the result is written back to the
        Execution Context.
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether this agent's dependencies are reachable and it is fit to run."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Concrete lifecycle hooks
    # ------------------------------------------------------------------

    async def on_start(self, context: ExecutionContext) -> None:
        """Default pre-execution hook: emits a structured start log entry.

        Subclasses that override this method should call
        `await super().on_start(context)` to preserve base logging.
        """
        self._logger.info(
            "agent_started",
            extra={
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "workflow_id": getattr(context, "workflow_id", None),
                "trace_id": getattr(context, "trace_id", None),
            },
        )

    async def on_complete(self, context: ExecutionContext, output_data: BaseModel) -> None:
        """Default post-execution hook: emits a structured completion log entry.

        Subclasses that override this method should call
        `await super().on_complete(context, output_data)` to preserve base logging.
        """
        self._logger.info(
            "agent_completed",
            extra={
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "workflow_id": getattr(context, "workflow_id", None),
                "trace_id": getattr(context, "trace_id", None),
            },
        )

    async def on_error(self, context: ExecutionContext, error: Exception) -> None:
        """Default error hook: emits a structured error log entry.

        Subclasses that override this method should call
        `await super().on_error(context, error)` to preserve base logging.
        """
        self._logger.error(
            "agent_error",
            extra={
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "workflow_id": getattr(context, "workflow_id", None),
                "trace_id": getattr(context, "trace_id", None),
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
            exc_info=error,
        )
