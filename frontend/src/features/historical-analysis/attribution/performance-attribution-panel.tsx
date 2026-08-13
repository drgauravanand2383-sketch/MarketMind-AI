import { lazy, Suspense, type ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { Skeleton } from "@/components/states/skeleton";
import { ContributionList } from "@/features/historical-analysis/explainability/contribution-list";
import type { AttributionCategory, ContributionBreakdown, PerformanceAttribution } from "@/types/explainability";

// Lazy-loaded — see `dashboard-card-registry.tsx` for why.
const AttributionBarChart = lazy(() =>
  import("@/features/historical-analysis/charts/attribution-bar-chart").then((m) => ({ default: m.AttributionBarChart })),
);
const ContributionDistributionChart = lazy(() =>
  import("@/features/historical-analysis/charts/contribution-distribution-chart").then((m) => ({ default: m.ContributionDistributionChart })),
);

function ChartFallback(): ReactNode {
  return <Skeleton className="h-56 w-full" />;
}

function AttributionChartFallback(): ReactNode {
  return <Skeleton className="h-52 w-full" />;
}

function signed(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function byCategory(breakdown: ContributionBreakdown[], category: AttributionCategory): ContributionBreakdown[] {
  return breakdown.filter((item) => item.category === category);
}

/**
 * `PerformanceAttribution.period` is a single label for the whole
 * backtest, not a time series — there is no per-period-over-time
 * attribution anywhere in the backend. Presented here as a
 * single-snapshot panel anchored to that one period/backtest run
 * (approved product decision, `docs/frontend/MILESTONE_6.md`), not an
 * evolving chart. Only populated when the explanation request supplied
 * a `backtest_run_id`.
 */
export function PerformanceAttributionPanel({ attribution }: { attribution: PerformanceAttribution | null }): ReactNode {
  if (!attribution) {
    return (
      <EmptyState
        icon="📊"
        title="No performance attribution"
        description="Supply a backtest run when generating the explanation to unlock this section."
      />
    );
  }

  const sector = byCategory(attribution.contribution_breakdown, "SECTOR");
  const country = byCategory(attribution.contribution_breakdown, "COUNTRY");
  const industry = byCategory(attribution.contribution_breakdown, "INDUSTRY");

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-slate-500 dark:text-slate-400">Period: {attribution.period}</p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
          <p className="text-xs text-slate-500 dark:text-slate-400">Portfolio return</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{signed(attribution.portfolio_return)}</p>
        </div>
        <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
          <p className="text-xs text-slate-500 dark:text-slate-400">Benchmark return</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{signed(attribution.benchmark_return)}</p>
        </div>
        <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
          <p className="text-xs text-slate-500 dark:text-slate-400">Excess return</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{signed(attribution.excess_return)}</p>
        </div>
      </div>

      <p className="text-sm text-slate-700 dark:text-slate-300">{attribution.summary}</p>

      <div>
        <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Category attribution (all sources)
        </h5>
        <Suspense fallback={<ChartFallback />}>
          <ContributionDistributionChart items={attribution.contribution_breakdown} />
        </Suspense>
        <div className="mt-2">
          <ContributionList items={attribution.contribution_breakdown} emptyMessage="No contribution breakdown reported." />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div>
          <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Sector attribution</h5>
          <Suspense fallback={<AttributionChartFallback />}>
            <AttributionBarChart items={sector} label="Sector attribution" color="#0ea5e9" />
          </Suspense>
        </div>
        <div>
          <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Country attribution</h5>
          <Suspense fallback={<AttributionChartFallback />}>
            <AttributionBarChart items={country} label="Country attribution" color="#8b5cf6" />
          </Suspense>
        </div>
        <div>
          <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Industry attribution</h5>
          <Suspense fallback={<AttributionChartFallback />}>
            <AttributionBarChart items={industry} label="Industry attribution" color="#22c55e" />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
