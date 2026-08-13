import type { ReactNode } from "react";
import { useHealth } from "@/hooks/use-health";
import { connectivityMessage, deriveConnectivityLevel } from "@/lib/connectivity";
import { useNetworkStatusStore } from "@/store/network-status-store";
import { useRealtimeConnectionStore } from "@/store/realtime-connection-store";

/**
 * Site-wide offline/degraded-connectivity awareness — mounted once in
 * `AppShell`, above `<Outlet />`, so it's visible from every page, not
 * only the dashboard's `ConnectivityPanel` card (a Milestone 9 audit
 * finding: a user on any other page while offline previously got zero
 * indication). Reuses the same `deriveConnectivityLevel`/
 * `connectivityMessage` derivation `ConnectivityPanel` already uses —
 * this banner is a lightweight, always-present summary; `ConnectivityPanel`
 * remains the detailed status view (API/WS/readiness/version), not
 * replaced by this.
 */
export function ConnectivityBanner(): ReactNode {
  const health = useHealth();
  const wsState = useRealtimeConnectionStore((state) => state.state);
  const online = useNetworkStatusStore((state) => state.online);

  const level = deriveConnectivityLevel(online, wsState, health.data?.state);
  const message = connectivityMessage(level);

  if (!message) return null;

  return (
    <p
      role="status"
      className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
    >
      {message}
    </p>
  );
}
