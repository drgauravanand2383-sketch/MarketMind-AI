import type { ReactNode } from "react";
import { PriorityBadge } from "@/components/priority-badge";
import { deriveRiskScores } from "@/features/decision-center/risk/derive-risk-scores";
import type { MarketDataCoverageStatus, RiskAssessment, RiskMetric } from "@/types/portfolio";

/** Milestone 14, purely informational — never affects `overall_risk_score`
 * itself (`app.risk.engine`'s own formulas are unchanged). `NOT_EVALUATED`
 * renders nothing, to avoid noise on the common case of an assessment
 * whose candidates never carried market data at all. */
const COVERAGE_LABELS: Partial<Record<MarketDataCoverageStatus, string>> = {
  FULL: "Live market data: full coverage",
  PARTIAL: "Live market data: partial coverage",
  NONE: "Live market data: unavailable",
};

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
  const coverageLabel = assessment.market_data_coverage
    ? COVERAGE_LABELS[assessment.market_data_coverage.status]
    : undefined;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Overall risk</p>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-xl font-semibold text-slate-900 dark:text-slate-100">{assessment.overall_risk_score.toFixed(0)}</span>
          <PriorityBadge level={assessment.overall_severity} />
        </div>
        {coverageLabel && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{coverageLabel}</p>}
      </div>
      <ScoreCard label="Diversification" metric={derived.diversification} />
      <ScoreCard label="Concentration" metric={derived.concentration} />
      <ScoreCard label="Liquidity" metric={derived.liquidity} />
      <ScoreCard label="Volatility" metric={derived.volatility} />
    </div>
  );
}
