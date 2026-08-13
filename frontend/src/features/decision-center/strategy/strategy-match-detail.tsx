import type { ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import type { RuleAlignment, StrategyMatch } from "@/types/strategy";

function RuleList({ title, rules }: { title: string; rules: RuleAlignment[] }): ReactNode {
  if (rules.length === 0) {
    return (
      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h4>
        <p className="text-sm text-slate-500 dark:text-slate-400">None.</p>
      </div>
    );
  }
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h4>
      <ul className="flex flex-col gap-1.5 text-sm">
        {rules.map((rule) => (
          <li key={rule.rule_id} className="flex flex-col gap-0.5 rounded-md border border-slate-200 px-2 py-1.5 dark:border-slate-800">
            <div className="flex items-center justify-between">
              <span className="font-medium text-slate-800 dark:text-slate-200">{rule.field}</span>
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {(rule.pass_rate * 100).toFixed(0)}% pass rate · {rule.evaluated_candidate_count} evaluated
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">{rule.reason}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Evaluation is population-level, not per-candidate (`StrategyMatch` has
 * no `ticker` field) — a rule's "outcome" is the fraction of candidates
 * that satisfied it (`pass_rate`), never a single pass/fail. */
export function StrategyMatchDetail({ match }: { match: StrategyMatch | null }): ReactNode {
  if (!match) {
    return <EmptyState title="Select a strategy" description="Choose a row from the comparison table to see its matched/failed rules." />;
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{match.strategy_name}</h3>
        <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{match.reasoning}</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
          <p className="text-xs text-slate-500 dark:text-slate-400">Alignment score</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{match.alignment_score.toFixed(0)}</p>
        </div>
        <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
          <p className="text-xs text-slate-500 dark:text-slate-400">Confidence</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{match.confidence.toFixed(0)}%</p>
        </div>
      </div>
      <RuleList title="Matched rules" rules={match.matched_rules} />
      <RuleList title="Failed rules" rules={match.failed_rules} />
    </div>
  );
}
