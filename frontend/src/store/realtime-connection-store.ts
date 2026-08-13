import { create } from "zustand";
import type { ConnectionState } from "@/services/websocket/ws-client";

interface RealtimeConnectionState {
  state: ConnectionState;
  lastEventAt: string | null;
  lastHeartbeatAt: string | null;
  reconnect: () => void;
}

/**
 * A read-only mirror of `useWebSocket`'s live state — written exclusively
 * by `useRealtimeSync` (the one and only `useWebSocket` caller, see that
 * hook's docstring), read by every other component that needs connection
 * status (`ConnectivityPanel`, the notification bell) without calling
 * `useWebSocket` a second time, which would tear down the shared
 * connection on that second caller's unmount.
 */
export const useRealtimeConnectionStore = create<RealtimeConnectionState>()(() => ({
  state: "disconnected",
  lastEventAt: null,
  lastHeartbeatAt: null,
  reconnect: () => {
    // Replaced by `useRealtimeSync` with the real `WebSocketClient`
    // binding once it mounts; a no-op before then (there is nothing to
    // reconnect to yet).
  },
}));
