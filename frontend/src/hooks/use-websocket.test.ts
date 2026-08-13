import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useWebSocket } from "@/hooks/use-websocket";
import { installFakeWebSocket, type FakeWebSocket } from "@/test/mock-websocket";

describe("useWebSocket", () => {
  let lastSocket: () => FakeWebSocket;

  beforeEach(() => {
    ({ lastSocket } = installFakeWebSocket());
  });

  afterEach(() => {
    // Nothing to unstub explicitly — `installFakeWebSocket` re-stubs
    // fresh each test.
  });

  it("connects on mount and reports 'connected' once the socket opens", () => {
    const { result } = renderHook(() => useWebSocket());
    expect(result.current.state).toBe("connecting");

    act(() => {
      lastSocket().simulateOpen();
    });

    expect(result.current.state).toBe("connected");
  });

  it("records lastEventAt from an inbound 'event' message and lastHeartbeatAt from a 'pong'", () => {
    const { result } = renderHook(() => useWebSocket());
    act(() => {
      lastSocket().simulateOpen();
    });
    expect(result.current.lastEventAt).toBeNull();
    expect(result.current.lastHeartbeatAt).toBeNull();

    act(() => {
      lastSocket().simulateMessage({ type: "pong" });
    });
    expect(result.current.lastHeartbeatAt).not.toBeNull();

    act(() => {
      lastSocket().simulateMessage({
        type: "event",
        metadata: { connection_id: "c1", delivered_at: "2026-01-01T00:00:00Z" },
        event: {
          event_id: "e1",
          event_type: "HEALTH_STATUS_CHANGED",
          timestamp: "2026-01-01T00:05:00Z",
          correlation_id: null,
          payload: { state: "HEALTHY", repositories: [], services: [], dependencies: [], checked_at: "2026-01-01T00:05:00Z", summary: "ok" },
        },
      });
    });
    expect(result.current.lastEventAt).toBe("2026-01-01T00:05:00Z");
  });

  it("exposes a reconnect() that re-attempts the connection", () => {
    const { result } = renderHook(() => useWebSocket());
    act(() => {
      lastSocket().simulateOpen();
    });

    act(() => {
      lastSocket().close();
    });
    expect(result.current.state).toBe("disconnected");

    act(() => {
      result.current.reconnect();
    });
    expect(["connecting", "reconnecting"]).toContain(result.current.state);
  });

  it("disconnects the underlying client on unmount", () => {
    const { unmount } = renderHook(() => useWebSocket());
    act(() => {
      lastSocket().simulateOpen();
    });
    const socket = lastSocket();

    unmount();

    expect(socket.readyState).toBe(3);
  });
});
