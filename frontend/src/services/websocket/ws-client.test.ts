import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WebSocketClient } from "@/services/websocket/ws-client";
import { installFakeWebSocket } from "@/test/mock-websocket";

describe("WebSocketClient", () => {
  let lastSocket: ReturnType<typeof installFakeWebSocket>["lastSocket"];

  beforeEach(() => {
    ({ lastSocket } = installFakeWebSocket());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("appends the token as a query parameter and transitions to 'connected' on open", () => {
    const client = new WebSocketClient({ url: "ws://localhost/ws", getToken: () => "abc123" });
    client.connect();

    expect(lastSocket().url).toBe("ws://localhost/ws?token=abc123");
    expect(client.getState()).toBe("connecting");

    lastSocket().simulateOpen();
    expect(client.getState()).toBe("connected");
  });

  it("sends a subscribe message once connected", () => {
    const client = new WebSocketClient({ url: "ws://localhost/ws", getToken: () => null });
    client.connect();
    lastSocket().simulateOpen();

    client.subscribe(["HEALTH_STATUS_CHANGED"]);

    const sent: unknown = JSON.parse(lastSocket().sent.at(-1) ?? "{}");
    expect(sent).toEqual({ action: "subscribe", event_types: ["HEALTH_STATUS_CHANGED"] });
  });

  it("replays active subscriptions after a reconnect", () => {
    const client = new WebSocketClient({ url: "ws://localhost/ws", getToken: () => null });
    client.connect();
    lastSocket().simulateOpen();
    client.subscribe(["HEALTH_STATUS_CHANGED"]);

    const firstSocket = lastSocket();
    firstSocket.sent = [];
    vi.useFakeTimers();
    firstSocket.onclose?.();
    vi.advanceTimersByTime(1100);
    vi.useRealTimers();
    lastSocket().simulateOpen();

    const sentMessages = lastSocket().sent.map((raw: string): unknown => JSON.parse(raw));
    expect(sentMessages).toContainEqual({ action: "subscribe", event_types: ["HEALTH_STATUS_CHANGED"] });
  });

  it("disconnect() closes the socket and does not schedule a reconnect", () => {
    const client = new WebSocketClient({ url: "ws://localhost/ws", getToken: () => null });
    client.connect();
    lastSocket().simulateOpen();

    client.disconnect();

    expect(client.getState()).toBe("disconnected");
  });

  it("force-closes a socket that never opens once connectTimeoutMs elapses", () => {
    const client = new WebSocketClient({ url: "ws://localhost/ws", getToken: () => null, connectTimeoutMs: 5_000 });
    vi.useFakeTimers();
    client.connect();
    const socket = lastSocket();
    expect(socket.readyState).toBe(0);

    vi.advanceTimersByTime(5_000);

    expect(socket.readyState).toBe(3);
  });

  it("transitions to 'failed' once maxReconnectAttempts is exhausted, and reconnect() recovers from it", () => {
    const client = new WebSocketClient({
      url: "ws://localhost/ws",
      getToken: () => null,
      maxReconnectAttempts: 2,
      reconnectBaseDelayMs: 100,
    });
    vi.useFakeTimers();
    client.connect();
    lastSocket().onclose?.(); // attempt 1 scheduled
    vi.advanceTimersByTime(100);
    lastSocket().onclose?.(); // attempt 2 scheduled
    vi.advanceTimersByTime(200);
    lastSocket().onclose?.(); // attempts exhausted

    expect(client.getState()).toBe("failed");

    client.reconnect();
    expect(client.getState()).toBe("connecting");
    lastSocket().simulateOpen();
    expect(client.getState()).toBe("connected");
  });

  it("reconnect() is a no-op while already connected", () => {
    const client = new WebSocketClient({ url: "ws://localhost/ws", getToken: () => null });
    client.connect();
    lastSocket().simulateOpen();

    client.reconnect();

    expect(client.getState()).toBe("connected");
  });
});
