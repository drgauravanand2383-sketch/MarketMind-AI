"""Shared test doubles and helpers for Agent Planning Engine tests."""

from __future__ import annotations

from pydantic import BaseModel

from app.agents.base import AgentLayer, BaseAgent
from app.planning.models import StepInputPayload


class NoOpMemory:
    async def read(self, key: str) -> object:
        raise NotImplementedError

    async def write(self, key: str, value: object) -> None:
        raise NotImplementedError


class FakeOutput(BaseModel):
    ok: bool = True


class FakeAgent(BaseAgent):
    """A real, minimal `BaseAgent` used only to prove a `PlanningEngine`
    result is genuinely executable by the real `AgentOrchestrator` —
    planning tests otherwise never execute anything."""

    def __init__(self, agent_id: str = "fake-agent") -> None:
        super().__init__(NoOpMemory())
        self._agent_id = agent_id
        self.calls: list[StepInputPayload] = []

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def agent_name(self) -> str:
        return self._agent_id

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
        return StepInputPayload

    @property
    def output_schema(self) -> type[BaseModel]:
        return FakeOutput

    async def validate_input(self, input_data: BaseModel) -> bool:
        return isinstance(input_data, StepInputPayload)

    async def validate_output(self, output_data: BaseModel) -> bool:
        return isinstance(output_data, FakeOutput)

    async def health_check(self) -> bool:
        return True

    async def run(self, context, input_data: BaseModel) -> BaseModel:  # noqa: ANN001
        assert isinstance(input_data, StepInputPayload)
        self.calls.append(input_data)
        return FakeOutput()
