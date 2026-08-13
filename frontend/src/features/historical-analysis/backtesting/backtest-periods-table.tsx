import { useMemo, type ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { useHistoricalAnalysisUiStore } from "@/store/historical-analysis-ui-store";
import type { BacktestPeriod } from "@/types/backtesting";

/** `GET /backtests/{run_id}` returns every period in one unpaginated
 * array — no server-side search/filter exists for it, so the search box
 * is the same reasoned client-side exception Milestone 4/5 established
 * for screening/signal results. */
export function BacktestPeriodsTable({ periods }: { periods: BacktestPeriod[] }): ReactNode {
  const search = useHistoricalAnalysisUiStore((state) => state.periodsSearch);
  const setSearch = useHistoricalAnalysisUiStore((state) => state.setPeriodsSearch);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return periods;
    return periods.filter((period) => period.notes.toLowerCase().includes(needle));
  }, [periods, search]);

  return (
    <div className="flex flex-col gap-3">
      <label htmlFor="periods-search" className="sr-only">
        Search periods by note
      </label>
      <input
        id="periods-search"
        type="search"
        data-shortcut-target="search"
        placeholder="Search period notes…"
        value={search}
        onChange={(event) => {
          setSearch(event.target.value);
        }}
        className="w-full max-w-sm rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />

      {filtered.length === 0 ? (
        <EmptyState title="No periods match" description="Try clearing the search, or this backtest genuinely has no periods." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Historical periods</caption>
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800">
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Timestamp
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Portfolio value
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Benchmark value
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Return
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Notes
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((period) => (
                <tr key={period.timestamp} className="border-b border-slate-100 dark:border-slate-800/60">
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{new Date(period.timestamp).toLocaleString()}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{period.portfolio_value.toFixed(2)}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{period.benchmark_value?.toFixed(2) ?? "—"}</td>
                  <td className={`px-3 py-2 font-medium ${period.return_percent >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
                    {period.return_percent >= 0 ? "+" : ""}
                    {period.return_percent.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">{period.notes || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
