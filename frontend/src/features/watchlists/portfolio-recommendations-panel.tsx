import type { ReactNode } from "react";
import { ErrorState } from "@/components/states/error-state";
import { Skeleton } from "@/components/states/skeleton";
import { InitialAnalysisEmptyState } from "@/components/portfolio/initial-analysis-empty-state";
import { usePortfolioRecommendations } from "@/hooks/use-portfolio";

/** Only *availability* — this milestone has no UI for generating new
 * recommendations or browsing individual candidates (M3 spec: "No ...
 * recommendations ... UI yet"). */
export function PortfolioRecommendationsPanel({ portfolioId }: { portfolioId: string }): ReactNode {
  const recommendations = usePortfolioRecommendations(portfolioId);

  if (recommendations.isPending) return <Skeleton className="h-10 w-full" />;

  if (recommendations.isUnavailable) {
    return <InitialAnalysisEmptyState portfolioId={portfolioId} kind="recommendations" />;
  }

  if (recommendations.isError) {
    return (
      <ErrorState
        title="Couldn't check recommendation availability"
        message={recommendations.error?.message ?? "Unknown error."}
        onRetry={() => {
          void recommendations.refetch();
        }}
      />
    );
  }

  const data = recommendations.data;
  if (!data) return null;

  return (
    <div className="flex items-center gap-3">
      <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-500/10 dark:text-green-400">
        Available
      </span>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        {data.total_candidates} candidate{data.total_candidates === 1 ? "" : "s"} · {data.summary.strong_buy} strong buy ·{" "}
        {data.summary.buy} buy · {data.summary.watch} watch
      </p>
    </div>
  );
}
