import type { ReactNode } from "react";
import { PriorityBadge } from "@/components/priority-badge";
import { deriveRiskScores } from "@/features/decision-center/risk/derive-risk-scores";
import type { RiskAssessment, RiskMetric } from "@/types/portfolio";

function ScoreCard({ label, metric }: { label: string; metric: RiskMetric | null }): ReactNode {
  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      {metric ? (
        <>
          <div className="mt-1 flex items-center gap-2">
            <span className="text-xl font-semibold text-slate-900 dark:text-slate-100">{metric.score.toFixed(0)}</span>
            <PriorityBadge level={metric.severity} />
          </div>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{metric.description}</p>
        </>
      ) : (
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Not reported for this portfolio.</p>
      )}
    </div>
  );
}

/** `RiskAssessment` has no flat diversification/concentration/liquidity/
 * volatility field — these four cards derive them from `risk_metrics`
 * (`deriveRiskScores`), each falling back to an explicit "not reported"
 * state rather than showing a fabricated 0 when the engine genuinely
 * didn't emit that category for this portfolio. */
export function RiskScoreCards({ assessment }: { assessment: RiskAssessment }): ReactNode {
  const derived = deriveRiskScores(assessment.risk_metrics);

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Overall risk</p>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-xl font-semibold text-slate-900 dark:text-slate-100">{assessment.overall_risk_score.toFixed(0)}</span>
          <PriorityBadge level={assessment.overall_severity} />
        </div>
      </div>
      <ScoreCard label="Diversification" metric={derived.diversification} />
      <ScoreCard label="Concentration" metric={derived.concentration} />
      <ScoreCard label="Liquidity" metric={derived.liquidity} />
      <ScoreCard label="Volatility" metric={derived.volatility} />
    </div>
  );
}
