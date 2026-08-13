import type { ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { EmptyState } from "@/components/states/empty-state";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { useGenerateExplanation } from "@/hooks/use-explainability";
import { useDecisionHistoryStore } from "@/store/decision-history-store";

const generateFormSchema = z.object({
  name: z.string().min(1, "Name is required"),
  recommendation_result_id: z.string().min(1, "Select a recommendation result"),
  strategy_evaluation_id: z.string(),
  risk_assessment_id: z.string(),
  backtest_run_id: z.string(),
});

type GenerateFormValues = z.infer<typeof generateFormSchema>;

const SELECT_CLASS =
  "rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

/**
 * `recommendation_result_id` is required — every explanation ultimately
 * traces back to a `RecommendationResult` (`app/explainability/models.py`).
 * The three optional ids each unlock one extra section of the result
 * (strategy/risk/performance-attribution). There is no backend endpoint
 * to list/search these ids — this session's own Decision Center/
 * Historical Analysis activity is the only source (same approved
 * decision the Backtesting snapshot builder uses).
 */
export function GenerateExplanationForm(): ReactNode {
  const navigate = useNavigate();
  const generate = useGenerateExplanation();
  const allEntries = useDecisionHistoryStore((state) => state.entries);
  const recommendationEntries = allEntries.filter((e) => e.kind === "recommendations_generated");
  const strategyEntries = allEntries.filter((e) => e.kind === "strategy_evaluated");
  const riskEntries = allEntries.filter((e) => e.kind === "risk_loaded");
  const backtestEntries = allEntries.filter((e) => e.kind === "backtest_run");

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<GenerateFormValues>({
    resolver: zodResolver(generateFormSchema),
    defaultValues: { name: "", recommendation_result_id: "", strategy_evaluation_id: "", risk_assessment_id: "", backtest_run_id: "" },
  });

  const submit = handleSubmit((values: GenerateFormValues) => {
    generate.mutate(
      {
        name: values.name,
        recommendation_result_id: values.recommendation_result_id,
        ...(values.strategy_evaluation_id && { strategy_evaluation_id: values.strategy_evaluation_id }),
        ...(values.risk_assessment_id && { risk_assessment_id: values.risk_assessment_id }),
        ...(values.backtest_run_id && { backtest_run_id: values.backtest_run_id }),
      },
      {
        onSuccess: (result) => {
          void navigate({ to: "/historical-analysis/explainability/$requestId", params: { requestId: result.request_id } });
        },
      },
    );
  });

  if (recommendationEntries.length === 0) {
    return (
      <EmptyState
        icon="🧭"
        title="No recommendation results this session yet"
        description="Generate a recommendation in the Decision Center first — every explanation traces back to one."
      />
    );
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4" noValidate aria-busy={generate.isPending}>
      <FormField label="Name" autoComplete="off" error={errors.name?.message} {...register("name")} />

      <div className="flex flex-col gap-1">
        <label htmlFor="recommendation_result_id" className="text-sm font-medium text-slate-700 dark:text-slate-300">
          Recommendation result
        </label>
        <select id="recommendation_result_id" className={SELECT_CLASS} {...register("recommendation_result_id")}>
          <option value="">Select…</option>
          {recommendationEntries.map((entry) => (
            <option key={entry.requestId} value={entry.requestId}>
              {entry.candidateCount} candidates — {new Date(entry.occurredAt).toLocaleString()}
            </option>
          ))}
        </select>
        {errors.recommendation_result_id && (
          <p role="alert" className="text-xs text-red-600 dark:text-red-400">
            {errors.recommendation_result_id.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="strategy_evaluation_id" className="text-sm font-medium text-slate-700 dark:text-slate-300">
          Strategy evaluation (optional — unlocks strategy explanations)
        </label>
        <select id="strategy_evaluation_id" className={SELECT_CLASS} {...register("strategy_evaluation_id")}>
          <option value="">None</option>
          {strategyEntries.map((entry) => (
            <option key={entry.requestId} value={entry.requestId}>
              {entry.bestStrategy ?? "Evaluated"} — {new Date(entry.occurredAt).toLocaleString()}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="risk_assessment_id" className="text-sm font-medium text-slate-700 dark:text-slate-300">
          Risk assessment (optional — unlocks the risk explanation)
        </label>
        <select id="risk_assessment_id" className={SELECT_CLASS} {...register("risk_assessment_id")}>
          <option value="">None</option>
          {riskEntries.map((entry) => (
            <option key={entry.requestId} value={entry.requestId}>
              {new Date(entry.occurredAt).toLocaleString()}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="backtest_run_id" className="text-sm font-medium text-slate-700 dark:text-slate-300">
          Backtest run (optional — unlocks performance attribution)
        </label>
        <select id="backtest_run_id" className={SELECT_CLASS} {...register("backtest_run_id")}>
          <option value="">None</option>
          {backtestEntries.map((entry) => (
            <option key={entry.runId} value={entry.runId}>
              {entry.name} — {new Date(entry.occurredAt).toLocaleString()}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3">
        <LoadingButton isLoading={generate.isPending} loadingText="Generating…">
          Generate explanation
        </LoadingButton>
      </div>
    </form>
  );
}
