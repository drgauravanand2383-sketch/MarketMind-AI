import { useMemo, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { EmptyState } from "@/components/states/empty-state";
import { useDecisionHistoryStore } from "@/store/decision-history-store";

/** This session's own backtest runs — there is no `GET /backtests` list
 * endpoint (each run is only reachable by its own `run_id`), so a "run
 * history" can only ever be what this browser session itself created. */
export function RunHistoryList(): ReactNode {
  const allEntries = useDecisionHistoryStore((state) => state.entries);
  const entries = useMemo(() => allEntries.filter((e) => e.kind === "backtest_run"), [allEntries]);

  if (entries.length === 0) {
    return <EmptyState icon="🕓" title="No backtests run yet this session" description="Run a backtest above to see it here." />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {entries.map((entry) => (
        <li key={entry.id} className="flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800">
          <div className="min-w-0">
            <Link to="/historical-analysis/backtests/$runId" params={{ runId: entry.runId }} className="font-medium text-brand-700 hover:underline dark:text-brand-400">
              {entry.name}
            </Link>
            <p className="text-xs text-slate-500 dark:text-slate-400">{new Date(entry.occurredAt).toLocaleString()}</p>
          </div>
          <span className={`shrink-0 text-sm font-medium ${entry.portfolioReturn >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
            {entry.portfolioReturn >= 0 ? "+" : ""}
            {entry.portfolioReturn.toFixed(2)}%
          </span>
        </li>
      ))}
    </ul>
  );
}
