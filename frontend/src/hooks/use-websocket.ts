import { useCallback, useEffect, useRef, useState } from "react";
import { WebSocketClient, type ConnectionState } from "@/services/websocket/ws-client";
import { WS_BASE_URL } from "@/services/api/config";
import { getAccessTokenValue } from "@/store/auth-store";
import type { EventType, ServerMessage } from "@/types/websocket";

/**
 * Owns one `WebSocketClient` instance for the lifetime of the component
 * tree that mounts it, connects on mount, disconnects on unmount, and
 * exposes the live connection state plus a way to subscribe to specific
 * event types.
 *
 * **Exactly one component may call this hook for the lifetime of an
 * authenticated session** — `WebSocketClient.disconnect()` fires
 * unconditionally on unmount, so a second caller would tear down the
 * first's connection. That one caller is `useRealtimeSync`
 * (`src/hooks/use-realtime-sync.ts`), mounted once in `AppShell`; every
 * other consumer (`ConnectivityPanel`, the notification bell, etc.)
 * reads the Zustand mirror `useRealtimeConnectionStore` instead of
 * calling this hook a second time.
 */
export function useWebSocket(eventTypes: EventType[] = []): {
  state: ConnectionState;
  lastMessage: ServerMessage | null;
  lastEventAt: string | null;
  lastHeartbeatAt: string | null;
  reconnect: () => void;
} {
  const clientRef = useRef<WebSocketClient | null>(null);
  const [state, setState] = useState<ConnectionState>("disconnected");
  const [lastMessage, setLastMessage] = useState<ServerMessage | null>(null);
  const [lastEventAt, setLastEventAt] = useState<string | null>(null);
  const [lastHeartbeatAt, setLastHeartbeatAt] = useState<string | null>(null);

  clientRef.current ??= new WebSocketClient({ url: WS_BASE_URL, getToken: getAccessTokenValue });

  useEffect(() => {
    const client = clientRef.current;
    if (!client) return;

    const unsubscribeState = client.onStateChange(setState);
    const unsubscribeMessages = client.onMessage((message) => {
      setLastMessage(message);
      if (message.type === "event") {
        setLastEventAt(message.event.timestamp);
      } else if (message.type === "pong") {
        setLastHeartbeatAt(new Date().toISOString());
      }
    });
    client.connect();

    return () => {
      unsubscribeState();
      unsubscribeMessages();
      client.disconnect();
    };
  }, []);

  useEffect(() => {
    if (state !== "connected" || eventTypes.length === 0) return;
    clientRef.current?.subscribe(eventTypes);
    return () => {
      clientRef.current?.unsubscribe(eventTypes);
    };
  }, [state, eventTypes]);

  const reconnect = useCallback(() => {
    clientRef.current?.reconnect();
  }, []);

  return { state, lastMessage, lastEventAt, lastHeartbeatAt, reconnect };
}
