import { useState, type ReactNode } from "react";
import { LoadingButton } from "@/components/forms/loading-button";
import { EmptyState } from "@/components/states/empty-state";
import { SkeletonList } from "@/components/states/skeleton";
import { useStrategiesList } from "@/hooks/use-strategy";

export interface StrategyEvaluateFormProps {
  recommendationResultId: string;
  isPending: boolean;
  onSubmit: (strategyIds: string[]) => void;
}

/** Lets the user optionally narrow which strategies to evaluate against
 * — leaving every checkbox unchecked evaluates every strategy in one
 * call and returns them ranked (`strategy_ids: []` means "all", per the
 * real backend contract), which is also how "strategy comparison" is
 * served: there's no separate comparison endpoint. */
export function StrategyEvaluateForm({ recommendationResultId, isPending, onSubmit }: StrategyEvaluateFormProps): ReactNode {
  const strategies = useStrategiesList({ page: 1, page_size: 100, sort: "name", direction: "asc" });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  function toggle(id: string): void {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id]));
  }

  if (strategies.isPending) return <SkeletonList rows={3} rowClassName="h-8 w-full" />;

  if (strategies.isSuccess && strategies.data.data.length === 0) {
    return <EmptyState title="No strategies defined" description="No investment strategies exist to evaluate against yet." />;
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(selectedIds);
      }}
      className="flex flex-col gap-3"
      aria-busy={isPending}
    >
      <fieldset className="flex flex-col gap-1.5">
        <legend className="text-xs font-medium text-slate-500 dark:text-slate-400">
          Strategies to evaluate (none selected = every strategy)
        </legend>
        {strategies.data?.data.map((strategy) => (
          <label key={strategy.id} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" checked={selectedIds.includes(strategy.id)} onChange={() => { toggle(strategy.id); }} />
            {strategy.name}
          </label>
        ))}
      </fieldset>
      <div className="flex items-center gap-3">
        <LoadingButton isLoading={isPending} loadingText="Evaluating…" disabled={!recommendationResultId}>
          Evaluate strategies
        </LoadingButton>
        {!recommendationResultId && (
          <p className="text-sm text-slate-500 dark:text-slate-400">Generate recommendations first — strategy evaluation needs a recommendation result to score against.</p>
        )}
        {isPending && (
          <p role="status" aria-live="polite" className="text-sm text-slate-500 dark:text-slate-400">
            Evaluating…
          </p>
        )}
      </div>
    </form>
  );
}
