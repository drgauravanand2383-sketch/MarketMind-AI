import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { ExportPlaceholderMenu } from "@/components/export-placeholder-menu";
import { Panel } from "@/components/panel";
import { PerformanceAttributionPanel } from "@/features/historical-analysis/attribution/performance-attribution-panel";
import { RecommendationExplanationsList } from "@/features/historical-analysis/explainability/recommendation-explanations-list";
import { RiskExplanationPanel } from "@/features/historical-analysis/explainability/risk-explanation-panel";
import { StrategyExplanationsList } from "@/features/historical-analysis/explainability/strategy-explanations-list";
import { useComparisonStore } from "@/store/comparison-store";
import { useHistoricalAnalysisUiStore } from "@/store/historical-analysis-ui-store";
import type { ExplainabilityResult } from "@/types/explainability";

export function ExplainabilityResultPanel({ result }: { result: ExplainabilityResult }): ReactNode {
  const compareIds = useComparisonStore((state) => state.explainabilityRequestIds);
  const toggleCompare = useComparisonStore((state) => state.toggleExplainabilityResult);
  const isSelectedForCompare = compareIds.includes(result.request_id);
  const showDataLabels = useHistoricalAnalysisUiStore((state) => state.chartPreferences.showDataLabels);
  const toggleShowDataLabels = useHistoricalAnalysisUiStore((state) => state.toggleShowDataLabels);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Request ID {result.request_id}</p>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{result.overall_summary}</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={showDataLabels} onChange={toggleShowDataLabels} />
            Show chart labels
          </label>
          <button
            type="button"
            aria-pressed={isSelectedForCompare}
            onClick={() => {
              toggleCompare(result.request_id);
            }}
            className={
              isSelectedForCompare
                ? "rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
                : "rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            }
          >
            {isSelectedForCompare ? "Selected for comparison" : "Add to comparison"}
          </button>
          {compareIds.length >= 2 && (
            <Link
              to="/historical-analysis/explainability/compare"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Compare selected ({compareIds.length})
            </Link>
          )}
          <ExportPlaceholderMenu />
        </div>
      </div>

      <Panel title="Recommendation explanations">
        <RecommendationExplanationsList explanations={result.recommendation_explanations} />
      </Panel>

      <Panel title="Strategy explanations">
        <StrategyExplanationsList explanations={result.strategy_explanations} />
      </Panel>

      <Panel title="Risk explanation">
        <RiskExplanationPanel explanation={result.risk_explanation} />
      </Panel>

      <Panel title="Performance attribution">
        <PerformanceAttributionPanel attribution={result.performance_attribution} />
      </Panel>
    </div>
  );
}
