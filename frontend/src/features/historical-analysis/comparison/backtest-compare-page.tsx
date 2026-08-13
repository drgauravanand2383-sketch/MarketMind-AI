import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { EmptyState } from "@/components/states/empty-state";
import { SkeletonList } from "@/components/states/skeleton";
import { useBacktestResults } from "@/hooks/use-backtesting";
import { useComparisonStore } from "@/store/comparison-store";
import type { BacktestResult } from "@/types/backtesting";

interface ComparisonRow {
  label: string;
  values: [string, string];
  differs: boolean;
}

function signed(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function buildRows(a: BacktestResult, b: BacktestResult): ComparisonRow[] {
  const rows: [string, string, string][] = [
    ["Portfolio return", signed(a.portfolio_return), signed(b.portfolio_return)],
    ["Benchmark return", signed(a.benchmark_return), signed(b.benchmark_return)],
    ["Excess return", signed(a.excess_return), signed(b.excess_return)],
    ["Max drawdown", `${a.max_drawdown.toFixed(2)}%`, `${b.max_drawdown.toFixed(2)}%`],
    ["Win rate", `${a.win_rate.toFixed(1)}%`, `${b.win_rate.toFixed(1)}%`],
    ["Periods processed", String(a.total_periods), String(b.total_periods)],
    ["Successful periods", String(a.successful_periods), String(b.successful_periods)],
    ["Failed periods", String(a.failed_periods), String(b.failed_periods)],
    ["Generated at", new Date(a.generated_at).toLocaleString(), new Date(b.generated_at).toLocaleString()],
  ];
  return rows.map(([label, valueA, valueB]) => ({ label, values: [valueA, valueB], differs: valueA !== valueB }));
}

/** Compares exactly the two backtests selected via `useComparisonStore`
 * (capped at 2) — presents already-fetched fields side by side and
 * flags where they differ; computes nothing new. */
export function BacktestComparePage(): ReactNode {
  const compareIds = useComparisonStore((state) => state.backtestRunIds);
  const clear = useComparisonStore((state) => state.clearBacktestRuns);
  const [idA, idB] = compareIds;

  const resultA = useBacktestResults(idA ?? "");
  const resultB = useBacktestResults(idB ?? "");

  if (compareIds.length < 2) {
    return (
      <div className="p-6">
        <EmptyState
          icon="⚖️"
          title="Select two backtests to compare"
          description='Open a backtest and click "Add to comparison" — do this for two runs to see them here.'
        />
      </div>
    );
  }

  if (resultA.isPending || resultB.isPending) {
    return (
      <div className="p-6">
        <SkeletonList rows={6} rowClassName="h-10 w-full" />
      </div>
    );
  }

  if (resultA.isError || resultB.isError) {
    return (
      <div className="p-6">
        <EmptyState icon="⚠" title="One or both backtests couldn't be loaded" description="Check the run ids and try again." />
      </div>
    );
  }

  const rows = buildRows(resultA.data, resultB.data);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Compare backtests</h1>
        <button
          type="button"
          onClick={clear}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Clear selection
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Backtest comparison</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Field
              </th>
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                <Link to="/historical-analysis/backtests/$runId" params={{ runId: idA ?? "" }} className="hover:underline">
                  Run A
                </Link>
              </th>
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                <Link to="/historical-analysis/backtests/$runId" params={{ runId: idB ?? "" }} className="hover:underline">
                  Run B
                </Link>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className={`border-b border-slate-100 dark:border-slate-800/60 ${row.differs ? "bg-amber-50 dark:bg-amber-500/10" : ""}`}>
                <td className="px-3 py-2 font-medium text-slate-700 dark:text-slate-300">{row.label}</td>
                <td className="px-3 py-2 text-slate-800 dark:text-slate-200">{row.values[0]}</td>
                <td className="px-3 py-2 text-slate-800 dark:text-slate-200">{row.values[1]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
