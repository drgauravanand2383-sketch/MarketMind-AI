import { useMemo, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { EmptyState } from "@/components/states/empty-state";
import { useDecisionHistoryStore, type DecisionHistoryEntry } from "@/store/decision-history-store";

function describeEntry(entry: DecisionHistoryEntry): { label: string; to?: { to: string; params: Record<string, string> } } | null {
  switch (entry.kind) {
    case "backtest_run":
      return {
        label: `Backtest "${entry.name}" — ${entry.portfolioReturn >= 0 ? "+" : ""}${entry.portfolioReturn.toFixed(2)}%`,
        to: { to: "/historical-analysis/backtests/$runId", params: { runId: entry.runId } },
      };
    case "explainability_generated":
      return {
        label: "Explanation generated",
        to: { to: "/historical-analysis/explainability/$requestId", params: { requestId: entry.requestId } },
      };
    default:
      return null;
  }
}

/** This session's own Historical Analysis activity — see
 * `store/decision-history-store.ts`'s module docstring for why there is
 * no durable, cross-session history to show instead. */
export function HistoricalAnalysisHistoryList(): ReactNode {
  const allEntries = useDecisionHistoryStore((state) => state.entries);
  const entries = useMemo(
    () => allEntries.filter((entry) => entry.kind === "backtest_run" || entry.kind === "explainability_generated"),
    [allEntries],
  );

  if (entries.length === 0) {
    return <EmptyState icon="🕓" title="No historical analysis yet this session" description="Run a backtest or generate an explanation to see it here." />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {entries.map((entry) => {
        const described = describeEntry(entry);
        if (!described) return null;
        return (
          <li key={entry.id} className="flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
            {described.to ? (
              <Link to={described.to.to} params={described.to.params} className="text-brand-700 hover:underline dark:text-brand-400">
                {described.label}
              </Link>
            ) : (
              <span className="text-slate-700 dark:text-slate-300">{described.label}</span>
            )}
            <span className="shrink-0 text-xs text-slate-500 dark:text-slate-400">{new Date(entry.occurredAt).toLocaleString()}</span>
          </li>
        );
      })}
    </ul>
  );
}
