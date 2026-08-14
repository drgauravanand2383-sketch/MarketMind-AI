import type { ReactNode } from "react";
import type { MarketSnapshotStatus } from "@/types/portfolio";

/** Milestone 14. Mirrors `app.services.market_snapshot.models
 * .MarketSnapshotStatus` exactly — never re-interpreted or coarsened.
 * Grouped into 3 visual buckets (fresh / stale / unavailable-or-unmapped)
 * for a compact badge, the same "shared color scale, per-domain labels"
 * approach `PriorityBadge` already established — but every status still
 * renders its own exact label, never collapsed into a bucket name. */
const STATUS_STYLES: Record<MarketSnapshotStatus, string> = {
  FRESH: "bg-green-100 text-green-800 dark:bg-green-500/10 dark:text-green-400",
  STALE: "bg-amber-100 text-amber-800 dark:bg-amber-500/10 dark:text-amber-400",
  ENTITY_NOT_MAPPED: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  PROVIDER_UNAVAILABLE: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  PROVIDER_TIMEOUT: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  RATE_LIMITED: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  INVALID_RESPONSE: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  NO_DATA: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  UNAVAILABLE: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

const STATUS_LABELS: Record<MarketSnapshotStatus, string> = {
  FRESH: "Fresh",
  STALE: "Stale",
  ENTITY_NOT_MAPPED: "Not mapped",
  PROVIDER_UNAVAILABLE: "Unavailable",
  PROVIDER_TIMEOUT: "Timed out",
  RATE_LIMITED: "Rate limited",
  INVALID_RESPONSE: "Invalid response",
  NO_DATA: "No data",
  UNAVAILABLE: "Unavailable",
};

export function MarketFreshnessBadge({ status }: { status: MarketSnapshotStatus }): ReactNode {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}
