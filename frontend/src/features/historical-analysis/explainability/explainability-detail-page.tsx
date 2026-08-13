import type { ReactNode } from "react";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { ExplainabilityResultPanel } from "@/features/historical-analysis/explainability/explainability-result-panel";
import { useExplainabilityResult } from "@/hooks/use-explainability";

/** Unlike Research/Screening/Signals, Explainability results are
 * durably persisted via a real `BaseExplainabilityRepository` — not the
 * in-memory `InMemoryResultStore` M4/M5 flagged for those domains
 * (confirmed against `app/explainability/engine.py`). A 404 here means
 * this request id genuinely doesn't exist (a bad link or typo), not
 * "the backend restarted" — so it's shown as a plain error, not a
 * special "no longer available" empty state. */
export function ExplainabilityDetailPage({ requestId }: { requestId: string }): ReactNode {
  const result = useExplainabilityResult(requestId);

  if (result.isPending) {
    return (
      <div className="p-6">
        <SkeletonList rows={6} rowClassName="h-10 w-full" />
      </div>
    );
  }

  if (result.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title="Couldn't load this explanation"
          message={result.error.message}
          onRetry={() => {
            void result.refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-6">
      <ExplainabilityResultPanel result={result.data} />
    </div>
  );
}
