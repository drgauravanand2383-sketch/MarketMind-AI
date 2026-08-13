import type { ReactNode } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "@/components/states/empty-state";
import { useBacktestMarkersStore } from "@/store/backtest-markers-store";
import { useHistoricalAnalysisUiStore, type TimelineMetric } from "@/store/historical-analysis-ui-store";
import type { BacktestPeriod } from "@/types/backtesting";

const METRIC_OPTIONS: { id: TimelineMetric; label: string }[] = [
  { id: "portfolio", label: "Portfolio" },
  { id: "benchmark", label: "Benchmark" },
  { id: "both", label: "Both" },
];

function formatTick(value: string): string {
  return new Date(value).toLocaleDateString();
}

/**
 * The only backend source for a timeline is `BacktestRun.results`
 * (the `BacktestPeriod` array) — there is no "major events" field
 * anywhere. Recommendation markers are rendered only when
 * `useBacktestMarkersStore` has an entry for this `runId` (i.e. the
 * backtest was created in the current browser session) — the backend
 * itself never preserves which `recommendation_result_id` fed a given
 * period, so a run loaded by id from an earlier session renders the
 * timeline without markers, explained via the empty note below the
 * chart rather than silently.
 */
export function HistoricalTimeline({ runId, periods }: { runId: string; periods: BacktestPeriod[] }): ReactNode {
  const metric = useHistoricalAnalysisUiStore((state) => state.timelineMetric);
  const setMetric = useHistoricalAnalysisUiStore((state) => state.setTimelineMetric);
  const markers = useBacktestMarkersStore((state) => state.markersByRunId[runId]);

  if (periods.length === 0) {
    return <EmptyState title="No periods to plot" description="This backtest has no periods — nothing to show on the timeline." />;
  }

  const data = periods.map((period) => ({
    timestamp: period.timestamp,
    portfolio_value: period.portfolio_value,
    benchmark_value: period.benchmark_value,
  }));

  const markerDots = (markers ?? [])
    .map((marker) => {
      const period = periods.find((p) => p.timestamp === marker.timestamp);
      return period ? { timestamp: period.timestamp, value: period.portfolio_value } : null;
    })
    .filter((dot): dot is { timestamp: string; value: number } => dot !== null);

  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label="Timeline metric" className="flex gap-1">
        {METRIC_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            aria-pressed={metric === option.id}
            onClick={() => {
              setMetric(option.id);
            }}
            className={
              metric === option.id
                ? "rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white"
                : "rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            }
          >
            {option.label}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} aria-label="Historical timeline: portfolio and benchmark value over time">
          <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
          <XAxis dataKey="timestamp" tickFormatter={formatTick} tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip labelFormatter={(value) => (typeof value === "string" || typeof value === "number" ? new Date(value).toLocaleString() : "")} />
          <Legend />
          {(metric === "portfolio" || metric === "both") && (
            <Line type="monotone" dataKey="portfolio_value" name="Portfolio" stroke="#0ea5e9" dot={false} strokeWidth={2} />
          )}
          {(metric === "benchmark" || metric === "both") && (
            <Line type="monotone" dataKey="benchmark_value" name="Benchmark" stroke="#94a3b8" dot={false} strokeWidth={2} />
          )}
          {markerDots.map((dot) => (
            <ReferenceDot key={dot.timestamp} x={dot.timestamp} y={dot.value} r={5} fill="#f59e0b" stroke="none" />
          ))}
        </LineChart>
      </ResponsiveContainer>

      {markers === undefined && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          No recommendation markers to show — this run wasn't created in the current browser session, so which
          recommendation fed each period isn't available (the backend doesn't retain that mapping).
        </p>
      )}
      {markers && markers.length > 0 && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          <span aria-hidden="true" className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-500" />
          Amber dots mark periods fed by a recommendation result generated this session.
        </p>
      )}
    </div>
  );
}
