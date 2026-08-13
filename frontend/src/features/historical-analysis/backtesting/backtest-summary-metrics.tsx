import type { ReactNode } from "react";
import type { BacktestResult } from "@/types/backtesting";

function MetricCard({ label, value, tone }: { label: string; value: string; tone?: "positive" | "negative" | undefined }): ReactNode {
  const toneClass = tone === "positive" ? "text-green-700 dark:text-green-400" : tone === "negative" ? "text-red-700 dark:text-red-400" : "text-slate-900 dark:text-slate-100";
  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}

function signed(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function toneFor(value: number): "positive" | "negative" | undefined {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return undefined;
}

/** Every value here is a plain backend-returned percentage number
 * (`app/backtesting/models.py` — confirmed none are 0-1 fractions).
 * "Success ratio" has no dedicated backend field — it's a simple
 * presentational ratio of two already-provided integers
 * (`successful_periods`/`total_periods`), the same "X of Y" derivation
 * Milestone 4's screening results table already established. */
export function BacktestSummaryMetrics({ result }: { result: BacktestResult }): ReactNode {
  const successRatio = result.total_periods === 0 ? 0 : (result.successful_periods / result.total_periods) * 100;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MetricCard label="Portfolio return" value={signed(result.portfolio_return)} tone={toneFor(result.portfolio_return)} />
      <MetricCard label="Benchmark return" value={signed(result.benchmark_return)} tone={toneFor(result.benchmark_return)} />
      <MetricCard label="Excess return" value={signed(result.excess_return)} tone={toneFor(result.excess_return)} />
      <MetricCard label="Max drawdown" value={`${result.max_drawdown.toFixed(2)}%`} tone={result.max_drawdown > 0 ? "negative" : undefined} />
      <MetricCard label="Win rate" value={`${result.win_rate.toFixed(1)}%`} />
      <MetricCard label="Periods processed" value={String(result.total_periods)} />
      <MetricCard
        label="Success ratio"
        value={`${String(result.successful_periods)}/${String(result.total_periods)} (${successRatio.toFixed(0)}%)`}
      />
      <MetricCard label="Failed periods" value={String(result.failed_periods)} tone={result.failed_periods > 0 ? "negative" : undefined} />
    </div>
  );
}
