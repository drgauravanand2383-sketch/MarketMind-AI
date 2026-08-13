import type { ReactNode } from "react";
import type { HealthState } from "@/types/health";

export type BadgeState = HealthState | "CONNECTED" | "DISCONNECTED" | "UNKNOWN" | "CONNECTING" | "RECONNECTING" | "FAILED";

const STATE_STYLES: Record<BadgeState, string> = {
  HEALTHY: "bg-green-100 text-green-800 dark:bg-green-500/10 dark:text-green-400",
  DEGRADED: "bg-amber-100 text-amber-800 dark:bg-amber-500/10 dark:text-amber-400",
  UNHEALTHY: "bg-red-100 text-red-800 dark:bg-red-500/10 dark:text-red-400",
  CONNECTED: "bg-green-100 text-green-800 dark:bg-green-500/10 dark:text-green-400",
  DISCONNECTED: "bg-red-100 text-red-800 dark:bg-red-500/10 dark:text-red-400",
  UNKNOWN: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  CONNECTING: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  RECONNECTING: "bg-amber-100 text-amber-800 dark:bg-amber-500/10 dark:text-amber-400",
  FAILED: "bg-red-100 text-red-800 dark:bg-red-500/10 dark:text-red-400",
};

export function StatusBadge({ state }: { state: BadgeState }): ReactNode {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATE_STYLES[state]}`}>{state}</span>;
}
