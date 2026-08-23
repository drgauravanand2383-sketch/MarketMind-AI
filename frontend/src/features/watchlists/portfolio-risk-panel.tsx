import type { ReactNode } from "react";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { PriorityBadge } from "@/components/priority-badge";
import { InitialAnalysisEmptyState } from "@/components/portfolio/initial-analysis-empty-state";
import { usePortfolioRisk } from "@/hooks/use-portfolio";

export function PortfolioRiskPanel({ portfolioId }: { portfolioId: string }): ReactNode {
  const risk = usePortfolioRisk(portfolioId);

  if (risk.isPending) return <SkeletonList rows={3} rowClassName="h-10 w-full" />;

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

  const data = risk.data;
  if (!data) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{data.overall_risk_score.toFixed(0)}</span>
        <PriorityBadge level={data.overall_severity} />
      </div>
      <p className="text-sm text-slate-600 dark:text-slate-300">{data.summary}</p>

      {data.risk_metrics.length > 0 && (
        <ul className="flex flex-col gap-2">
          {data.risk_metrics.map((metric) => (
            <li
              key={metric.metric_name}
              className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm dark:border-slate-800"
            >
              <div>
                <p className="font-medium text-slate-900 dark:text-slate-100">{metric.metric_name}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">{metric.description}</p>
              </div>
              <PriorityBadge level={metric.severity} />
            </li>
          ))}
        </ul>
      )}

      {data.recommendations.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400">Recommendations</h3>
          <ul className="mt-1 list-inside list-disc text-sm text-slate-600 dark:text-slate-300">
            {data.recommendations.map((recommendation) => (
              <li key={recommendation}>{recommendation}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
