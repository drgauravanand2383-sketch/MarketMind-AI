"""A minimal fake WebSocket for unit-testing `ConnectionManager` without a
real ASGI transport — just enough surface (`accept`, `send_text`) for the
manager to drive, plus a way to simulate a dead connection.
"""

from __future__ import annotations

__all__ = ["FakeWebSocket"]


class FakeWebSocket:
    def __init__(self, *, fail_on_send: bool = False) -> None:
        self.accepted = False
        self.sent: list[str] = []
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        if self.fail_on_send:
            raise RuntimeError("simulated dead connection")
        self.sent.append(data)
