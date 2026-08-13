import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Panel } from "@/components/panel";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { Skeleton, SkeletonList } from "@/components/states/skeleton";
import { GenerateRecommendationsForm } from "@/features/decision-center/recommendations/generate-recommendations-form";
import { RecommendationDetailPanel } from "@/features/decision-center/recommendations/recommendation-detail-panel";
import { RecommendationList } from "@/features/decision-center/recommendations/recommendation-list";
import { RecommendationSummaryCards } from "@/features/decision-center/recommendations/recommendation-summary-cards";
import { usePortfolioRecommendations } from "@/hooks/use-portfolio";
import { useDecisionWorkspaceStore } from "@/store/decision-workspace-store";

// Lazy-loaded — see `dashboard-card-registry.tsx` for why.
const RecommendationScoreDistributionChart = lazy(() =>
  import("@/features/decision-center/charts/recommendation-score-distribution-chart").then((m) => ({
    default: m.RecommendationScoreDistributionChart,
  })),
);

function ChartFallback(): ReactNode {
  return <Skeleton className="h-56 w-full" />;
}

export function RecommendationsPanel({ portfolioId }: { portfolioId: string }): ReactNode {
  const recommendations = usePortfolioRecommendations(portfolioId);
  const setActiveRecommendationResultId = useDecisionWorkspaceStore((state) => state.setActiveRecommendationResultId);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  // Threads the loaded `RecommendationResult.request_id` into the
  // workspace store so the Strategy tab can reference it without a
  // second portfolio-scoped fetch — see `docs/frontend/MILESTONE_5.md`'s
  // "portfolio-centered, partial sync" design.
  useEffect(() => {
    setActiveRecommendationResultId(recommendations.data?.request_id ?? null);
  }, [recommendations.data?.request_id, setActiveRecommendationResultId]);

  if (!portfolioId) {
    return <EmptyState icon="💡" title="Select a portfolio" description="Pick a watchlist above to generate or view recommendations." />;
  }

  return (
    <div className="flex flex-col gap-6">
      <Panel title="Generate recommendations">
        <GenerateRecommendationsForm portfolioId={portfolioId} />
      </Panel>

      {recommendations.isPending && <SkeletonList rows={5} rowClassName="h-10 w-full" />}

      {recommendations.isUnavailable && (
        <EmptyState
          icon="💡"
          title="No recommendations yet"
          description="Generate recommendations above to see candidates for this portfolio."
        />
      )}

      {recommendations.isError && (
        <ErrorState
          title="Couldn't load recommendations"
          message={recommendations.error?.message ?? "Unknown error."}
          onRetry={() => {
            void recommendations.refetch();
          }}
        />
      )}

      {recommendations.isSuccess && (
        <>
          <RecommendationSummaryCards summary={recommendations.data.summary} />
          <Panel title="Score distribution">
            <Suspense fallback={<ChartFallback />}>
              <RecommendationScoreDistributionChart candidates={recommendations.data.recommendations} />
            </Suspense>
          </Panel>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Candidates">
              <RecommendationList
                candidates={recommendations.data.recommendations}
                selectedTicker={selectedTicker}
                onSelect={setSelectedTicker}
              />
            </Panel>
            <Panel title="Detail">
              <RecommendationDetailPanel
                candidate={recommendations.data.recommendations.find((c) => c.ticker === selectedTicker) ?? null}
              />
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
