import type { ReactNode } from "react";

/** Every 4-tier priority/severity scale across the backend (`RiskSeverity`
 * — `LOW`/`MODERATE`/`HIGH`/`CRITICAL`; `SignalPriority`/`AlertPriority`
 * — `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`) uses the same underlying color
 * scale, just with `MODERATE`/`MEDIUM` naming the same middle tier
 * differently per domain — one shared badge covers both label sets. */
export type PriorityLevel = "LOW" | "MODERATE" | "MEDIUM" | "HIGH" | "CRITICAL";

const LEVEL_STYLES: Record<PriorityLevel, string> = {
  LOW: "bg-green-100 text-green-800 dark:bg-green-500/10 dark:text-green-400",
  MODERATE: "bg-amber-100 text-amber-800 dark:bg-amber-500/10 dark:text-amber-400",
  MEDIUM: "bg-amber-100 text-amber-800 dark:bg-amber-500/10 dark:text-amber-400",
  HIGH: "bg-orange-100 text-orange-800 dark:bg-orange-500/10 dark:text-orange-400",
  CRITICAL: "bg-red-100 text-red-800 dark:bg-red-500/10 dark:text-red-400",
};

export function PriorityBadge({ level }: { level: PriorityLevel }): ReactNode {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${LEVEL_STYLES[level]}`}>{level}</span>;
}
