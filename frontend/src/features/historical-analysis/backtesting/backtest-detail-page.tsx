import { lazy, Suspense, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { ExportPlaceholderMenu } from "@/components/export-placeholder-menu";
import { Panel } from "@/components/panel";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { Skeleton, SkeletonList } from "@/components/states/skeleton";
import { BacktestPeriodsTable } from "@/features/historical-analysis/backtesting/backtest-periods-table";
import { BacktestSummaryMetrics } from "@/features/historical-analysis/backtesting/backtest-summary-metrics";
import { useBacktestResults, useBacktestRun } from "@/hooks/use-backtesting";
import { useComparisonStore } from "@/store/comparison-store";
import { useHistoricalAnalysisUiStore } from "@/store/historical-analysis-ui-store";

// Lazy-loaded — see `dashboard-card-registry.tsx` for why (Recharts is
// the single largest bundle chunk, and none of these render until this
// page is actually visited).
const HistoricalTimeline = lazy(() =>
  import("@/features/historical-analysis/backtesting/historical-timeline").then((m) => ({ default: m.HistoricalTimeline })),
);
const DrawdownCurveChart = lazy(() =>
  import("@/features/historical-analysis/charts/drawdown-curve-chart").then((m) => ({ default: m.DrawdownCurveChart })),
);
const PortfolioVsBenchmarkChart = lazy(() =>
  import("@/features/historical-analysis/charts/portfolio-vs-benchmark-chart").then((m) => ({ default: m.PortfolioVsBenchmarkChart })),
);

function ChartFallback(): ReactNode {
  return <Skeleton className="h-56 w-full" />;
}

export function BacktestDetailPage({ runId }: { runId: string }): ReactNode {
  const run = useBacktestRun(runId);
  const results = useBacktestResults(runId);
  const compareIds = useComparisonStore((state) => state.backtestRunIds);
  const toggleCompare = useComparisonStore((state) => state.toggleBacktestRun);
  const isSelectedForCompare = compareIds.includes(runId);
  const showDataLabels = useHistoricalAnalysisUiStore((state) => state.chartPreferences.showDataLabels);
  const toggleShowDataLabels = useHistoricalAnalysisUiStore((state) => state.toggleShowDataLabels);

  if (run.isPending || results.isPending) {
    return (
      <div className="p-6">
        <SkeletonList rows={6} rowClassName="h-10 w-full" />
      </div>
    );
  }

  if (run.isError || results.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title="Couldn't load this backtest"
          message={(run.error ?? results.error)?.message ?? "Unknown error."}
          onRetry={() => {
            void run.refetch();
            void results.refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Backtest results</h1>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Run ID {runId}</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={showDataLabels} onChange={toggleShowDataLabels} />
            Show chart labels
          </label>
          <button
            type="button"
            aria-pressed={isSelectedForCompare}
            onClick={() => {
              toggleCompare(runId);
            }}
            className={
              isSelectedForCompare
                ? "rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
                : "rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            }
          >
            {isSelectedForCompare ? "Selected for comparison" : "Add to comparison"}
          </button>
          {compareIds.length >= 2 && (
            <Link
              to="/historical-analysis/backtests/compare"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Compare selected ({compareIds.length})
            </Link>
          )}
          <ExportPlaceholderMenu />
        </div>
      </div>

      <BacktestSummaryMetrics result={results.data} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Portfolio vs benchmark">
          <Suspense fallback={<ChartFallback />}>
            <PortfolioVsBenchmarkChart result={results.data} />
          </Suspense>
        </Panel>
        <Panel title="Drawdown curve">
          <Suspense fallback={<ChartFallback />}>
            <DrawdownCurveChart periods={run.data.results} />
          </Suspense>
        </Panel>
      </div>

      <Panel title="Timeline">
        <Suspense fallback={<ChartFallback />}>
          <HistoricalTimeline runId={runId} periods={run.data.results} />
        </Suspense>
      </Panel>

      <Panel title="Historical periods">
        {run.data.results.length === 0 ? (
          <EmptyState title="No periods recorded" description="This backtest ran with no snapshots, so it has no periods." />
        ) : (
          <BacktestPeriodsTable periods={run.data.results} />
        )}
      </Panel>

      <Panel title="Summary">
        <p className="text-sm text-slate-700 dark:text-slate-300">{results.data.summary}</p>
      </Panel>
    </div>
  );
}
