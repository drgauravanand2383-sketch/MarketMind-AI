import { lazy, Suspense, type ReactNode } from "react";
import { Panel } from "@/components/panel";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { Skeleton, SkeletonList } from "@/components/states/skeleton";
import { InitialAnalysisEmptyState } from "@/components/portfolio/initial-analysis-empty-state";
import { RiskExposurePanel } from "@/features/decision-center/risk/risk-exposure-panel";
import { RiskMetricsTable } from "@/features/decision-center/risk/risk-metrics-table";
import { RiskScoreCards } from "@/features/decision-center/risk/risk-score-cards";
import { useRiskLoadedEffects } from "@/features/decision-center/risk/use-risk-loaded-effects";
import { usePortfolioRisk } from "@/hooks/use-portfolio";

// Lazy-loaded — see `dashboard-card-registry.tsx` for why.
const RiskCategoryChart = lazy(() =>
  import("@/features/decision-center/charts/risk-category-chart").then((m) => ({ default: m.RiskCategoryChart })),
);
const ExposurePieChart = lazy(() =>
  import("@/features/decision-center/charts/exposure-pie-chart").then((m) => ({ default: m.ExposurePieChart })),
);

function ChartFallback(): ReactNode {
  return <Skeleton className="h-56 w-full" />;
}

export function RiskPanel({ portfolioId }: { portfolioId: string }): ReactNode {
  const risk = usePortfolioRisk(portfolioId);
  useRiskLoadedEffects(risk.data, portfolioId);

  if (!portfolioId) {
    return <EmptyState icon="⚠" title="Select a portfolio" description="Pick a watchlist above to load its risk assessment." />;
  }

  if (risk.isPending) {
    return <SkeletonList rows={5} rowClassName="h-10 w-full" />;
  }

  if (risk.isUnavailable) {
    return <InitialAnalysisEmptyState portfolioId={portfolioId} kind="risk assessment" />;
  }

  if (risk.isError) {
    return (
      <ErrorState
        title="Couldn't load risk assessment"
        message={risk.error?.message ?? "Unknown error."}
        onRetry={() => {
          void risk.refetch();
        }}
      />
    );
  }

  const assessment = risk.data;
  if (!assessment) return null;

  return (
    <div className="flex flex-col gap-6">
      <RiskScoreCards assessment={assessment} />

      <Panel title="Risk category breakdown">
        <Suspense fallback={<ChartFallback />}>
          <RiskCategoryChart metrics={assessment.risk_metrics} />
        </Suspense>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Sector exposure">
          <Suspense fallback={<ChartFallback />}>
            <ExposurePieChart exposures={assessment.exposures} dimension="sector" label="Sector exposure" />
          </Suspense>
        </Panel>
        <Panel title="Country exposure">
          <Suspense fallback={<ChartFallback />}>
            <ExposurePieChart exposures={assessment.exposures} dimension="country" label="Country exposure" />
          </Suspense>
        </Panel>
      </div>

      <Panel title="Exposure">
        <RiskExposurePanel exposures={assessment.exposures} />
      </Panel>

      <Panel title="Summary">
        <p className="text-sm text-slate-700 dark:text-slate-300">{assessment.summary}</p>
        {assessment.recommendations.length > 0 && (
          <ul className="mt-3 list-inside list-disc text-sm text-slate-600 dark:text-slate-300">
            {assessment.recommendations.map((recommendation) => (
              <li key={recommendation}>{recommendation}</li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="All risk metrics">
        <RiskMetricsTable metrics={assessment.risk_metrics} />
      </Panel>
    </div>
  );
}
