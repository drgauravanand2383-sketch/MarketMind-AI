import type { ConnectionState } from "@/services/websocket/ws-client";
import type { HealthState } from "@/types/health";

/**
 * The 3 states the Milestone 7 spec asks for ("offline", "server
 * unavailable", "degraded but reachable") are a pure derivation of two
 * already-tracked signals (`navigator.onLine` and the WebSocket
 * connection state, optionally combined with the already-polled backend
 * health) — no new combined store/enum needed. "Offline" wins regardless
 * of WS state, since a WS reconnect loop failing is meaningless noise
 * when the browser itself has no network.
 */
export type ConnectivityLevel = "offline" | "unreachable" | "degraded" | "online";

export function deriveConnectivityLevel(online: boolean, wsState: ConnectionState, healthState?: HealthState): ConnectivityLevel {
  if (!online) return "offline";
  if (wsState === "reconnecting" || wsState === "failed" || wsState === "disconnected") return "unreachable";
  if (healthState && healthState !== "HEALTHY") return "degraded";
  return "online";
}

export function connectivityMessage(level: ConnectivityLevel): string | null {
  switch (level) {
    case "offline":
      return "You're offline — check your internet connection.";
    case "unreachable":
      return "Real-time connection unavailable — some updates may be delayed.";
    case "degraded":
      return "Connected, but the backend is reporting degraded health.";
    case "online":
      return null;
  }
}
