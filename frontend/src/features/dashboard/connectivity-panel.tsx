import type { ReactNode } from "react";
import { Skeleton } from "@/components/states/skeleton";
import { connectivityMessage, deriveConnectivityLevel } from "@/lib/connectivity";
import { useHealth, useReadiness, useVersion } from "@/hooks/use-health";
import { StatusBadge, type BadgeState } from "@/features/dashboard/status-badge";
import { useNetworkStatusStore } from "@/store/network-status-store";
import { useRealtimeConnectionStore } from "@/store/realtime-connection-store";
import type { ConnectionState } from "@/services/websocket/ws-client";

function StatCard({ label, children }: { label: string; children: ReactNode }): ReactNode {
  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function connectivityState(isPending: boolean, isError: boolean, isConnected: boolean): BadgeState {
  if (isPending) return "UNKNOWN";
  if (isError) return "DISCONNECTED";
  return isConnected ? "CONNECTED" : "DISCONNECTED";
}

const WS_BADGE_STATE: Record<ConnectionState, BadgeState> = {
  connected: "CONNECTED",
  connecting: "CONNECTING",
  reconnecting: "RECONNECTING",
  failed: "FAILED",
  disconnected: "DISCONNECTED",
};

const WS_STATE_ANNOUNCEMENT: Record<ConnectionState, string> = {
  connected: "WebSocket connected",
  connecting: "WebSocket connecting",
  reconnecting: "WebSocket reconnecting",
  failed: "WebSocket connection failed",
  disconnected: "WebSocket disconnected",
};

function relativeOrNever(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "Never";
}

/** Reads the WebSocket connection state from `realtime-connection-store`
 * rather than calling `useWebSocket()` itself — `useRealtimeSync`
 * (mounted once in `AppShell`) owns the app's single WS connection; a
 * second `useWebSocket()` caller here would tear it down on this
 * component's own unmount. */
export function ConnectivityPanel(): ReactNode {
  const health = useHealth();
  const readiness = useReadiness();
  const version = useVersion();
  const wsState = useRealtimeConnectionStore((state) => state.state);
  const lastEventAt = useRealtimeConnectionStore((state) => state.lastEventAt);
  const lastHeartbeatAt = useRealtimeConnectionStore((state) => state.lastHeartbeatAt);
  const reconnect = useRealtimeConnectionStore((state) => state.reconnect);
  const online = useNetworkStatusStore((state) => state.online);

  const level = deriveConnectivityLevel(online, wsState, health.data?.state);
  const message = connectivityMessage(level);
  const showReconnect = wsState === "failed" || wsState === "disconnected";

  return (
    <div className="flex flex-col gap-3">
      {message && (
        <p role="status" className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {message}
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <StatCard label="API connectivity">
          <StatusBadge state={connectivityState(health.isPending, health.isError, health.isSuccess)} />
        </StatCard>
        <StatCard label="WebSocket connectivity">
          <div className="flex flex-col gap-1">
            <span aria-live="polite" className="sr-only">
              {WS_STATE_ANNOUNCEMENT[wsState]}
            </span>
            <div className="flex items-center gap-2">
              <StatusBadge state={WS_BADGE_STATE[wsState]} />
              {showReconnect && (
                <button
                  type="button"
                  onClick={reconnect}
                  className="rounded-md border border-slate-300 px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Reconnect
                </button>
              )}
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">Last event: {relativeOrNever(lastEventAt)}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Last heartbeat: {relativeOrNever(lastHeartbeatAt)}</p>
          </div>
        </StatCard>
        <StatCard label="Readiness">
          {readiness.isPending ? (
            <Skeleton className="h-5 w-20" />
          ) : (
            <StatusBadge state={connectivityState(false, readiness.isError, Boolean(readiness.data?.ready))} />
          )}
        </StatCard>
        <StatCard label="Version">
          {version.isPending ? (
            <Skeleton className="h-5 w-24" />
          ) : (
            <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
              {version.data ? `${version.data.application_version} (${version.data.environment})` : "Unavailable"}
            </p>
          )}
        </StatCard>
      </div>
    </div>
  );
}
