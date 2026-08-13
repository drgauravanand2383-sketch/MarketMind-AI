import { vi } from "vitest";
import type { DomainEvent, EventDeliveryMessage, EventMetadata, EventType, ServerMessage } from "@/types/websocket";

/**
 * A single shared fake `WebSocket` for tests — consolidates what used to
 * be 3 near-identical hand-rolled classes (`test/routing.test.tsx`,
 * `features/dashboard/dashboard-page.test.tsx`,
 * `services/websocket/ws-client.test.ts`) into one, per the project's
 * "every component should be reusable where practical" rule.
 */
export class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];

  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = 3;
    this.onclose?.();
  }

  simulateOpen(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  simulateMessage(message: ServerMessage): void {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  simulateClose(): void {
    this.close();
  }

  simulateError(): void {
    this.onerror?.();
  }
}

/** Stubs the global `WebSocket` with `FakeWebSocket` and resets its
 * instance registry — call from a test's `beforeEach`. */
export function installFakeWebSocket(): { lastSocket: () => FakeWebSocket } {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  return {
    lastSocket: () => {
      const socket = FakeWebSocket.instances.at(-1);
      if (!socket) throw new Error("No FakeWebSocket instance was created.");
      return socket;
    },
  };
}

type PayloadFor<T extends EventType> = Extract<DomainEvent, { event_type: T }>["payload"];

let nextEventId = 1;

/** Builds one well-formed `DomainEvent` around an existing domain
 * fixture (`buildAlert`, `buildBacktestResult`, etc.) — payload type is
 * enforced by `eventType` via `PayloadFor`, so passing a mismatched
 * fixture is a compile error, not a runtime surprise. */
export function buildDomainEvent<T extends EventType>(
  eventType: T,
  payload: PayloadFor<T>,
  overrides?: Partial<{ event_id: string; timestamp: string; correlation_id: string | null }>,
): Extract<DomainEvent, { event_type: T }> {
  return {
    event_type: eventType,
    event_id: overrides?.event_id ?? `test-event-${String(nextEventId++)}`,
    timestamp: overrides?.timestamp ?? "2026-02-01T00:00:00Z",
    correlation_id: overrides?.correlation_id ?? null,
    payload,
  } as Extract<DomainEvent, { event_type: T }>;
}

/** Wraps a `DomainEvent` in the full `{type:"event", metadata, event}`
 * envelope the real backend sends — see `EventDeliveryMessage`. */
export function buildEventEnvelope(event: DomainEvent, metadataOverrides?: Partial<EventMetadata>): EventDeliveryMessage {
  return {
    type: "event",
    metadata: { connection_id: "test-connection", delivered_at: "2026-02-01T00:00:00Z", ...metadataOverrides },
    event,
  };
}

/** One-call shortcut combining `buildDomainEvent` + `buildEventEnvelope`
 * — the shape most tests actually want to hand to `simulateMessage`. */
export function buildServerEventMessage<T extends EventType>(
  eventType: T,
  payload: PayloadFor<T>,
  overrides?: Partial<{ event_id: string; timestamp: string; correlation_id: string | null }>,
): EventDeliveryMessage {
  return buildEventEnvelope(buildDomainEvent(eventType, payload, overrides));
}
