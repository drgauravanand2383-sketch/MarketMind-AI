import type { ReactNode } from "react";
import { ContributionList } from "@/features/historical-analysis/explainability/contribution-list";
import type { StrategyExplanation } from "@/types/explainability";
import type { RuleAlignment } from "@/types/strategy";

function RuleList({ title, rules }: { title: string; rules: RuleAlignment[] }): ReactNode {
  if (rules.length === 0) {
    return (
      <div>
        <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h5>
        <p className="text-sm text-slate-500 dark:text-slate-400">None.</p>
      </div>
    );
  }
  return (
    <div>
      <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h5>
      <ul className="flex flex-col gap-1 text-sm">
        {rules.map((rule) => (
          <li key={rule.rule_id} className="rounded-md border border-slate-200 px-2 py-1.5 dark:border-slate-800">
            <div className="flex items-center justify-between">
              <span className="font-medium text-slate-800 dark:text-slate-200">{rule.field}</span>
              <span className="text-xs text-slate-500 dark:text-slate-400">{(rule.pass_rate * 100).toFixed(0)}% pass rate</span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">{rule.reason}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StrategyExplanationsList({ explanations }: { explanations: StrategyExplanation[] }): ReactNode {
  if (explanations.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No strategy evaluation was supplied for this explanation.</p>;
  }

  return (
    <ul className="flex flex-col gap-4">
      {explanations.map((explanation) => (
        <li key={explanation.strategy_name} className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-base font-semibold text-slate-900 dark:text-slate-100">{explanation.strategy_name}</h4>
            <span className="text-sm text-slate-600 dark:text-slate-300">alignment {explanation.alignment_score.toFixed(0)}</span>
          </div>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{explanation.summary}</p>
          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
            <RuleList title="Matched rules" rules={explanation.matched_rules} />
            <RuleList title="Failed rules" rules={explanation.failed_rules} />
            <div>
              <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Weight breakdown
              </h5>
              <ContributionList items={explanation.weight_breakdown} emptyMessage="No weight breakdown reported." />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
