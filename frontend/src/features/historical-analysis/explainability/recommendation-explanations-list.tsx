import type { ReactNode } from "react";
import { ContributionList } from "@/features/historical-analysis/explainability/contribution-list";
import type { RecommendationExplanation } from "@/types/explainability";

export function RecommendationExplanationsList({ explanations }: { explanations: RecommendationExplanation[] }): ReactNode {
  return (
    <ul className="flex flex-col gap-4">
      {explanations.map((explanation) => (
        <li key={explanation.ticker} className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              {explanation.ticker}
              {explanation.company_name && <span className="ml-2 text-sm font-normal text-slate-500 dark:text-slate-400">{explanation.company_name}</span>}
            </h4>
            <span className="text-sm text-slate-600 dark:text-slate-300">
              score {explanation.overall_score.toFixed(0)} · confidence {explanation.confidence.toFixed(0)}%
            </span>
          </div>

          <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">{explanation.reasoning}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{explanation.summary}</p>

          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
            <div>
              <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Top positive factors
              </h5>
              <ContributionList items={explanation.top_positive_factors} emptyMessage="No positive factors reported." />
            </div>
            <div>
              <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Top negative factors
              </h5>
              <ContributionList items={explanation.top_negative_factors} emptyMessage="No negative factors reported." />
            </div>
            <div>
              <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                All contributing components
              </h5>
              <ContributionList items={explanation.contributing_components} emptyMessage="No contributing components reported." />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
