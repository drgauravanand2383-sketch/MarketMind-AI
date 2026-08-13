import { lazy, Suspense, useState, type ReactNode } from "react";
import { Panel } from "@/components/panel";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { Skeleton } from "@/components/states/skeleton";
import { SignalDefinitionPicker } from "@/features/decision-center/signals/signal-definition-picker";
import { SignalEvaluateForm } from "@/features/decision-center/signals/signal-evaluate-form";
import { SignalResultsList } from "@/features/decision-center/signals/signal-results-list";
import { useEvaluateSignals, useSignalDefinitionsList } from "@/hooks/use-signals";

// Lazy-loaded — see `dashboard-card-registry.tsx` for why.
const SignalCategoryDistributionChart = lazy(() =>
  import("@/features/decision-center/charts/signal-category-distribution-chart").then((m) => ({ default: m.SignalCategoryDistributionChart })),
);

function ChartFallback(): ReactNode {
  return <Skeleton className="h-56 w-full" />;
}

/** Signal Detection has no portfolio concept at all (confirmed against
 * the real API surface) — this is a standalone tool within the
 * workspace, never auto-populated from the selected portfolio. */
export function SignalsPanel(): ReactNode {
  const definitions = useSignalDefinitionsList({ page: 1, page_size: 100, sort: "name", direction: "asc" });
  const [selectedDefinitionId, setSelectedDefinitionId] = useState("");
  const evaluateSignals = useEvaluateSignals();

  const selectedDefinition = definitions.data?.data.find((definition) => definition.id === selectedDefinitionId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <Panel title="Evaluate a signal">
        <div className="flex flex-col gap-4">
          <SignalDefinitionPicker selectedDefinitionId={selectedDefinitionId} onSelect={setSelectedDefinitionId} />
          {selectedDefinition ? (
            <SignalEvaluateForm
              definition={selectedDefinition}
              isPending={evaluateSignals.isPending}
              onSubmit={(snapshots) => {
                evaluateSignals.mutate({ definition_id: selectedDefinition.id, snapshots });
              }}
            />
          ) : (
            <EmptyState title="Select a definition" description="Pick a signal definition above to evaluate companies against it." />
          )}
        </div>
      </Panel>

      {evaluateSignals.isError && (
        <ErrorState
          title="Evaluation failed"
          message={evaluateSignals.error.message}
          onRetry={() => {
            evaluateSignals.mutate(evaluateSignals.variables);
          }}
        />
      )}

      {evaluateSignals.isSuccess && (
        <>
          <Panel title="Category distribution">
            <Suspense fallback={<ChartFallback />}>
              <SignalCategoryDistributionChart results={evaluateSignals.data.batch_result.signals} />
            </Suspense>
          </Panel>
          <Panel title="Results">
            <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{evaluateSignals.data.batch_result.summary}</p>
            <SignalResultsList results={evaluateSignals.data.batch_result.signals} />
          </Panel>
        </>
      )}
    </div>
  );
}
