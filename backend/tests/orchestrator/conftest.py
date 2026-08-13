"""Shared test doubles for Multi-Agent Orchestrator tests.

`FakeAgent` is a real `BaseAgent` implementation (not a mock) with full
call control — it can succeed, fail, delay, or report unhealthy, so
"mock only agent execution" (per the sprint's own instruction) is
satisfied literally: only what an agent *does* is faked, never the
orchestrator itself.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from app.agents.base import AgentLayer, BaseAgent


class NoOpMemory:
    async def read(self, key: str) -> object:
        raise NotImplementedError

    async def write(self, key: str, value: object) -> None:
        raise NotImplementedError


class TaskInput(BaseModel):
    value: int = 0


class TaskOutput(BaseModel):
    result: int


class FakeAgent(BaseAgent):
    """A fully working `BaseAgent` test double with configurable behavior.

    `multiplier`: `run()` returns `TaskOutput(result=input_data.value * multiplier)`.
    `error`: if set, `run()` raises it instead.
    `delay`: if set, `run()` awaits this many seconds before returning/raising
        (used to prove concurrent tasks in one wave overlap in time).
    `healthy`: `health_check()`'s return value.
    `health_check_error`: if set, `health_check()` raises it instead.
    """

    def __init__(
        self,
        agent_id: str = "fake-agent",
        multiplier: int = 1,
        error: Exception | None = None,
        delay: float = 0.0,
        healthy: bool = True,
        health_check_error: Exception | None = None,
    ) -> None:
        super().__init__(NoOpMemory())
        self._agent_id = agent_id
        self.multiplier = multiplier
        self.error = error
        self.delay = delay
        self.healthy = healthy
        self.health_check_error = health_check_error
        self.calls: list[TaskInput] = []

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def agent_name(self) -> str:
        return "Fake Agent"

    @property
    def version(self) -> str:
        return "0.0.0-test"

    @property
    def layer(self) -> AgentLayer:
        return AgentLayer.REASONING

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"fake"})

    @property
    def input_schema(self) -> type[BaseModel]:
        return TaskInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return TaskOutput

    async def validate_input(self, input_data: BaseModel) -> bool:
        return isinstance(input_data, TaskInput)

    async def validate_output(self, output_data: BaseModel) -> bool:
        return isinstance(output_data, TaskOutput)

    async def health_check(self) -> bool:
        if self.health_check_error is not None:
            raise self.health_check_error
        return self.healthy

    async def run(self, context, input_data: BaseModel) -> BaseModel:  # noqa: ANN001
        assert isinstance(input_data, TaskInput)
        self.calls.append(input_data)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return TaskOutput(result=input_data.value * self.multiplier)
