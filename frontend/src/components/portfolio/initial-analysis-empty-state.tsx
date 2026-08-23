import type { ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { useInitialAnalysisStatus, useTriggerInitialAnalysis } from "@/hooks/use-portfolio";

/** Shared by both the watchlist detail page's Risk/Recommendations panels
 * and the Decision Center's Risk/Recommendations panels (v1.2 Priority 8)
 * — the one place that turns `InitialAnalysisState` into the honest
 * ANALYZING/UNAVAILABLE/ERROR empty state a panel shows in place of "no
 * risk assessment yet" once a real initial-analysis job exists for this
 * portfolio. Never rendered for READY/PARTIAL — the caller renders its own
 * real data in that case, exactly as before this priority. */
export function InitialAnalysisEmptyState({
  portfolioId,
  kind,
}: {
  portfolioId: string;
  kind: "risk assessment" | "recommendations";
}): ReactNode {
  const analysisStatus = useInitialAnalysisStatus(portfolioId);
  const trigger = useTriggerInitialAnalysis();

  if (analysisStatus.isPending) {
    return <SkeletonList rows={3} rowClassName="h-10 w-full" />;
  }

  if (analysisStatus.isError) {
    // The status check itself failed (network/5xx) — distinct from the
    // analysis job having ended in ERROR (handled below from real data).
    return (
      <ErrorState
        title="Couldn't check analysis status"
        message={analysisStatus.error.message}
        onRetry={() => {
          void analysisStatus.refetch();
        }}
      />
    );
  }

  const state = analysisStatus.data;

  if (state.status === "ANALYZING") {
    return (
      <EmptyState
        icon="⏳"
        title={`Analyzing — ${kind} in progress`}
        description="Initial analysis runs automatically once a company is added to this portfolio. This can take a few seconds."
      />
    );
  }

  if (state.status === "ERROR") {
    return (
      <ErrorState
        title={`Initial ${kind} failed`}
        message={state.detail}
        onRetry={() => {
          trigger.mutate(portfolioId);
        }}
      />
    );
  }

  // UNAVAILABLE (or the rare READY/PARTIAL-with-no-cached-panel-data race,
  // which resolves itself on the next poll/WS invalidation).
  return <EmptyState icon="—" title={`No ${kind} yet`} description={state.detail} />;
}
