import { lazy, Suspense, useState, type ReactNode } from "react";
import { Panel } from "@/components/panel";
import { ErrorState } from "@/components/states/error-state";
import { Skeleton } from "@/components/states/skeleton";
import { StrategyComparisonTable } from "@/features/decision-center/strategy/strategy-comparison-table";
import { StrategyEvaluateForm } from "@/features/decision-center/strategy/strategy-evaluate-form";
import { StrategyMatchDetail } from "@/features/decision-center/strategy/strategy-match-detail";
import { useEvaluateStrategy } from "@/hooks/use-strategy";
import { useDecisionWorkspaceStore } from "@/store/decision-workspace-store";

// Lazy-loaded — see `dashboard-card-registry.tsx` for why.
const StrategyAlignmentChart = lazy(() =>
  import("@/features/decision-center/charts/strategy-alignment-chart").then((m) => ({ default: m.StrategyAlignmentChart })),
);

function ChartFallback(): ReactNode {
  return <Skeleton className="h-56 w-full" />;
}

export function StrategyPanel(): ReactNode {
  const activeRecommendationResultId = useDecisionWorkspaceStore((state) => state.activeRecommendationResultId);
  const evaluateStrategy = useEvaluateStrategy();
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-6">
      <Panel title="Evaluate">
        <StrategyEvaluateForm
          recommendationResultId={activeRecommendationResultId ?? ""}
          isPending={evaluateStrategy.isPending}
          onSubmit={(strategyIds) => {
            if (!activeRecommendationResultId) return;
            evaluateStrategy.mutate({ recommendation_result_id: activeRecommendationResultId, strategy_ids: strategyIds });
          }}
        />
      </Panel>

      {evaluateStrategy.isError && (
        <ErrorState
          title="Evaluation failed"
          message={evaluateStrategy.error.message}
          onRetry={() => {
            evaluateStrategy.mutate(evaluateStrategy.variables);
          }}
        />
      )}

      {evaluateStrategy.isSuccess && (
        <Panel title="Alignment by strategy">
          <Suspense fallback={<ChartFallback />}>
            <StrategyAlignmentChart matches={evaluateStrategy.data.strategy_matches} />
          </Suspense>
        </Panel>
      )}

      {evaluateStrategy.isSuccess && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Panel title="Comparison">
            <StrategyComparisonTable
              result={evaluateStrategy.data}
              selectedStrategyId={selectedStrategyId}
              onSelect={setSelectedStrategyId}
            />
          </Panel>
          <Panel title="Detail">
            <StrategyMatchDetail
              match={evaluateStrategy.data.strategy_matches.find((m) => m.strategy_id === selectedStrategyId) ?? null}
            />
          </Panel>
        </div>
      )}
    </div>
  );
}
