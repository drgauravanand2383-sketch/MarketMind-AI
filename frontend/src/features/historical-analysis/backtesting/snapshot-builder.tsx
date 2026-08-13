import { useState, type ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { draftsToSnapshots, emptySnapshotRow, type DraftSnapshot } from "@/features/historical-analysis/backtesting/snapshot-draft";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import type { HistoricalSnapshot } from "@/types/backtesting";

const INPUT_CLASS =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

/**
 * There is no backend endpoint to list/search existing
 * `RecommendationResult`/`StrategyEvaluationResult`/`RiskAssessment`
 * ids — each `HistoricalSnapshot` is built by picking from this
 * session's own Decision Center activity instead (approved product
 * decision, `docs/frontend/MILESTONE_6.md`). A backtest created in a
 * fresh session with no prior Decision Center activity has nothing to
 * pick from — the empty state below says so explicitly rather than
 * silently offering zero options.
 */
export function SnapshotBuilder({ onChange }: { onChange: (snapshots: HistoricalSnapshot[]) => void }): ReactNode {
  const allEntries = useDecisionHistoryStore((state) => state.entries);
  const recommendationEntries = allEntries.filter((e) => e.kind === "recommendations_generated");
  const strategyEntries = allEntries.filter((e) => e.kind === "strategy_evaluated");
  const riskEntries = allEntries.filter((e) => e.kind === "risk_loaded");

  const [rows, setRows] = useState<DraftSnapshot[]>(() => [emptySnapshotRow(new Date().toISOString().slice(0, 16))]);

  function updateRows(next: DraftSnapshot[]): void {
    setRows(next);
    onChange(draftsToSnapshots(next));
  }

  function updateRow(key: string, patch: Partial<DraftSnapshot>): void {
    updateRows(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  if (recommendationEntries.length === 0) {
    return (
      <EmptyState
        icon="🕓"
        title="No recommendation results this session yet"
        description="Generate a recommendation in the Decision Center first, then come back here to build a snapshot from it. A backtest can still be run with zero snapshots — it will simply have no periods."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Historical snapshots</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Timestamp
              </th>
              <th scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Recommendation result
              </th>
              <th scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Strategy evaluation
              </th>
              <th scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Risk assessment
              </th>
              <th scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Benchmark value
              </th>
              <th scope="col" className="px-2 py-1.5" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-b border-slate-100 dark:border-slate-800/60">
                <td className="px-2 py-1.5">
                  <label className="sr-only" htmlFor={`${row.key}-timestamp`}>
                    Timestamp
                  </label>
                  <input
                    id={`${row.key}-timestamp`}
                    type="datetime-local"
                    value={row.timestamp}
                    onChange={(event) => {
                      updateRow(row.key, { timestamp: event.target.value });
                    }}
                    className={INPUT_CLASS}
                  />
                </td>
                <td className="px-2 py-1.5">
                  <label className="sr-only" htmlFor={`${row.key}-rec`}>
                    Recommendation result
                  </label>
                  <select
                    id={`${row.key}-rec`}
                    value={row.recommendationResultId}
                    onChange={(event) => {
                      updateRow(row.key, { recommendationResultId: event.target.value });
                    }}
                    className={INPUT_CLASS}
                  >
                    <option value="">Select…</option>
                    {recommendationEntries.map((entry) => (
                      <option key={entry.requestId} value={entry.requestId}>
                        {entry.candidateCount} candidates — {new Date(entry.occurredAt).toLocaleString()}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1.5">
                  <label className="sr-only" htmlFor={`${row.key}-strat`}>
                    Strategy evaluation
                  </label>
                  <select
                    id={`${row.key}-strat`}
                    value={row.strategyEvaluationId}
                    onChange={(event) => {
                      updateRow(row.key, { strategyEvaluationId: event.target.value });
                    }}
                    className={INPUT_CLASS}
                  >
                    <option value="">None</option>
                    {strategyEntries.map((entry) => (
                      <option key={entry.requestId} value={entry.requestId}>
                        {entry.bestStrategy ?? "Evaluated"} — {new Date(entry.occurredAt).toLocaleString()}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1.5">
                  <label className="sr-only" htmlFor={`${row.key}-risk`}>
                    Risk assessment
                  </label>
                  <select
                    id={`${row.key}-risk`}
                    value={row.riskAssessmentId}
                    onChange={(event) => {
                      updateRow(row.key, { riskAssessmentId: event.target.value });
                    }}
                    className={INPUT_CLASS}
                  >
                    <option value="">None</option>
                    {riskEntries.map((entry) => (
                      <option key={entry.requestId} value={entry.requestId}>
                        {new Date(entry.occurredAt).toLocaleString()}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1.5">
                  <label className="sr-only" htmlFor={`${row.key}-benchmark`}>
                    Benchmark value
                  </label>
                  <input
                    id={`${row.key}-benchmark`}
                    type="number"
                    value={row.benchmarkValue}
                    onChange={(event) => {
                      updateRow(row.key, { benchmarkValue: event.target.value });
                    }}
                    className={`${INPUT_CLASS} w-28`}
                  />
                </td>
                <td className="px-2 py-1.5">
                  <button
                    type="button"
                    onClick={() => {
                      updateRows(rows.filter((r) => r.key !== row.key));
                    }}
                    disabled={rows.length <= 1}
                    aria-label="Remove snapshot"
                    className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-40 dark:text-red-400 dark:hover:bg-red-950"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        onClick={() => {
          updateRows([...rows, emptySnapshotRow(new Date().toISOString().slice(0, 16))]);
        }}
        className="self-start rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        Add snapshot
      </button>
    </div>
  );
}
