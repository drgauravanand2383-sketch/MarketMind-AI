import type { ClientMessage, EventType, ServerMessage } from "@/types/websocket";

export type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting" | "failed";

export interface WebSocketClientOptions {
  url: string;
  getToken: () => string | null;
  heartbeatIntervalMs?: number;
  maxReconnectAttempts?: number;
  reconnectBaseDelayMs?: number;
  connectTimeoutMs?: number;
}

type MessageHandler = (message: ServerMessage) => void;
type StateHandler = (state: ConnectionState) => void;

interface Subscription {
  eventTypes: EventType[];
  correlationId: string | undefined;
}

const DEFAULT_HEARTBEAT_INTERVAL_MS = 30_000;
const DEFAULT_MAX_RECONNECT_ATTEMPTS = 5;
const DEFAULT_RECONNECT_BASE_DELAY_MS = 1_000;
const DEFAULT_CONNECT_TIMEOUT_MS = 10_000;

/**
 * Typed client for the backend's `/ws` protocol
 * (`docs/architecture/WEBSOCKET_FRAMEWORK.md`, Sprint 59) — connect,
 * disconnect, reconnect with backoff, client-driven heartbeat, and
 * subscription management (replayed automatically across a reconnect,
 * since the backend holds no subscription state across connections).
 */
export class WebSocketClient {
  private readonly options: Required<WebSocketClientOptions>;
  private socket: WebSocket | null = null;
  private state: ConnectionState = "disconnected";
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private connectTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private deliberateDisconnect = false;
  private readonly activeSubscriptions = new Map<string, Subscription>();
  private readonly messageHandlers = new Set<MessageHandler>();
  private readonly stateHandlers = new Set<StateHandler>();

  constructor(options: WebSocketClientOptions) {
    this.options = {
      heartbeatIntervalMs: DEFAULT_HEARTBEAT_INTERVAL_MS,
      maxReconnectAttempts: DEFAULT_MAX_RECONNECT_ATTEMPTS,
      reconnectBaseDelayMs: DEFAULT_RECONNECT_BASE_DELAY_MS,
      connectTimeoutMs: DEFAULT_CONNECT_TIMEOUT_MS,
      ...options,
    };
  }

  getState(): ConnectionState {
    return this.state;
  }

  connect(): void {
    if (this.socket && (this.state === "connected" || this.state === "connecting")) return;
    this.deliberateDisconnect = false;
    this.openSocket();
  }

  disconnect(): void {
    this.deliberateDisconnect = true;
    this.clearHeartbeat();
    this.clearReconnectTimer();
    this.clearConnectTimeout();
    this.socket?.close(1000, "Client disconnected");
    this.socket = null;
    this.setState("disconnected");
  }

  /** User-visible "give up" recovery — resets the exhausted attempt
   * counter and starts a fresh connect attempt. A no-op if already
   * connected/connecting. */
  reconnect(): void {
    if (this.state === "connected" || this.state === "connecting") return;
    this.deliberateDisconnect = false;
    this.clearReconnectTimer(); // also resets `reconnectAttempts` to 0
    this.openSocket();
  }

  subscribe(eventTypes: EventType[], correlationId?: string): void {
    const subscription: Subscription = { eventTypes, correlationId };
    this.activeSubscriptions.set(subscriptionKey(subscription), subscription);
    this.send({ action: "subscribe", event_types: eventTypes, ...(correlationId !== undefined && { correlation_id: correlationId }) });
  }

  unsubscribe(eventTypes: EventType[], correlationId?: string): void {
    const subscription: Subscription = { eventTypes, correlationId };
    this.activeSubscriptions.delete(subscriptionKey(subscription));
    this.send({ action: "unsubscribe", event_types: eventTypes, ...(correlationId !== undefined && { correlation_id: correlationId }) });
  }

  /** Registers a handler for every inbound message; returns an
   * unsubscribe function. */
  onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  onStateChange(handler: StateHandler): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  private openSocket(): void {
    this.setState(this.reconnectAttempts > 0 ? "reconnecting" : "connecting");
    const token = this.options.getToken();
    const url = token ? `${this.options.url}?token=${encodeURIComponent(token)}` : this.options.url;
    const socket = new WebSocket(url);
    this.socket = socket;

    this.connectTimeoutTimer = setTimeout(() => {
      // Never opened, never errored/closed on its own — force it closed
      // so the existing `onclose` -> `scheduleReconnect` path runs,
      // rather than hanging in "connecting"/"reconnecting" forever.
      socket.close();
    }, this.options.connectTimeoutMs);

    socket.onopen = () => {
      this.clearConnectTimeout();
      this.reconnectAttempts = 0;
      this.setState("connected");
      this.startHeartbeat();
      this.resubscribeAll();
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      const message = safeParseServerMessage(event.data);
      if (message) {
        for (const handler of this.messageHandlers) handler(message);
      }
    };

    socket.onclose = () => {
      this.clearConnectTimeout();
      this.clearHeartbeat();
      this.socket = null;
      if (this.deliberateDisconnect) {
        this.setState("disconnected");
        return;
      }
      this.setState("disconnected");
      this.scheduleReconnect();
    };

    socket.onerror = () => {
      // `onclose` always follows `onerror` for a browser WebSocket — no
      // separate handling needed here beyond letting that path run.
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.options.maxReconnectAttempts) {
      this.setState("failed");
      return;
    }
    const delay = this.options.reconnectBaseDelayMs * 2 ** this.reconnectAttempts;
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.openSocket();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectAttempts = 0;
  }

  private clearConnectTimeout(): void {
    if (this.connectTimeoutTimer !== null) {
      clearTimeout(this.connectTimeoutTimer);
      this.connectTimeoutTimer = null;
    }
  }

  private startHeartbeat(): void {
    this.clearHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send({ action: "ping" });
    }, this.options.heartbeatIntervalMs);
  }

  private clearHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private resubscribeAll(): void {
    for (const subscription of this.activeSubscriptions.values()) {
      this.send({
        action: "subscribe",
        event_types: subscription.eventTypes,
        ...(subscription.correlationId !== undefined && { correlation_id: subscription.correlationId }),
      });
    }
  }

  private send(message: ClientMessage): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  private setState(state: ConnectionState): void {
    this.state = state;
    for (const handler of this.stateHandlers) handler(state);
  }
}

function subscriptionKey(subscription: Subscription): string {
  return `${subscription.eventTypes.slice().sort().join(",")}::${subscription.correlationId ?? ""}`;
}

function safeParseServerMessage(data: string): ServerMessage | null {
  try {
    return JSON.parse(data) as ServerMessage;
  } catch {
    return null;
  }
}
