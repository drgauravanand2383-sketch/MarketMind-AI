import type { ReactNode } from "react";
import type { DataFreshnessStatus, MarketSessionContext } from "@/types/global-markets";

const FRESHNESS_LABEL: Record<DataFreshnessStatus, string> = {
  LIVE: "Live",
  PREVIOUS_CLOSE: "Previous close",
  STALE: "Stale",
  UNAVAILABLE: "Unavailable",
};

const FRESHNESS_CLASS: Record<DataFreshnessStatus, string> = {
  LIVE: "bg-green-100 text-green-800 dark:bg-green-500/10 dark:text-green-400",
  PREVIOUS_CLOSE: "bg-blue-100 text-blue-800 dark:bg-blue-500/10 dark:text-blue-400",
  STALE: "bg-amber-100 text-amber-800 dark:bg-amber-500/10 dark:text-amber-400",
  UNAVAILABLE: "bg-red-100 text-red-800 dark:bg-red-500/10 dark:text-red-400",
};

function FreshnessPill({ status }: { status: DataFreshnessStatus }): ReactNode {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${FRESHNESS_CLASS[status]}`}>
      {FRESHNESS_LABEL[status]}
    </span>
  );
}

/** How current this **category's** data is, judged against that market's
 * own trading calendar — never wall-clock recency alone (see
 * `MarketSessionContext`'s own backend docstring). The "as of" session
 * date is always shown alongside the pill, never only in a hover
 * tooltip — PREVIOUS_CLOSE/STALE must never read as if they were LIVE.
 * `null` when the run carries no session context for this category at
 * all (e.g. the category itself failed before a session could be
 * resolved). */
export function DataFreshnessBadge({ context }: { context: MarketSessionContext | null | undefined }): ReactNode {
  if (!context) return null;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
      <FreshnessPill status={context.data_freshness_status} />
      <span>
        as of {context.market_session_date}
        {context.is_trading_now && " (market open)"}
      </span>
    </span>
  );
}

/** How current **this one asset's** own fetched value is
 * (`NormalizedAssetSnapshot.provenance`) — independent of, and may lag
 * behind, the category-level `MarketSessionContext` above (e.g. one
 * ticker's quote failed to refresh while the rest of the category
 * stayed LIVE). Shown in the ranked-asset table's expandable detail row
 * (never the main row) to keep the table itself uncluttered. */
export function AssetFreshnessNote({
  status,
  sourceTimestamp,
}: {
  status: DataFreshnessStatus;
  sourceTimestamp: string;
}): ReactNode {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
      <FreshnessPill status={status} />
      <span>as of {new Date(sourceTimestamp).toLocaleString()}</span>
    </span>
  );
}
