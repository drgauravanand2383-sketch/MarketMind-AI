import type { ReactNode } from "react";
import { PriorityBadge } from "@/components/priority-badge";
import { WeightedBarList } from "@/components/weighted-bar-list";
import type { RiskExplanation } from "@/types/explainability";
import type { RiskSeverity } from "@/types/portfolio";

const SEVERITY_ORDER: RiskSeverity[] = ["CRITICAL", "HIGH", "MODERATE", "LOW"];

/** `category_breakdown` reuses `RiskMetric` directly (a different,
 * more granular taxonomy than `AttributionCategory` — deliberately not
 * remapped, per the backend's own docstring); `exposure_breakdown`
 * reuses `PortfolioExposure` directly. Neither is recalculated. */
export function RiskExplanationPanel({ explanation }: { explanation: RiskExplanation | null }): ReactNode {
  if (!explanation) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No risk assessment was supplied for this explanation.</p>;
  }

  const sectors = explanation.exposure_breakdown.filter((e) => e.sector !== null).map((e) => ({ label: e.sector ?? "", weight: e.weight }));
  const countries = explanation.exposure_breakdown.filter((e) => e.country !== null).map((e) => ({ label: e.country ?? "", weight: e.weight }));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className="text-xl font-semibold text-slate-900 dark:text-slate-100">{explanation.overall_risk_score.toFixed(0)}</span>
        <span className="text-sm text-slate-500 dark:text-slate-400">overall risk score</span>
      </div>

      <p className="text-sm text-slate-700 dark:text-slate-300">{explanation.summary}</p>

      <div>
        <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Severity breakdown</h5>
        <div className="flex flex-wrap gap-2">
          {SEVERITY_ORDER.filter((severity) => explanation.severity_breakdown[severity]).map((severity) => (
            <div key={severity} className="flex items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 dark:border-slate-800">
              <PriorityBadge level={severity} />
              <span className="text-sm text-slate-700 dark:text-slate-300">{explanation.severity_breakdown[severity]}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Category breakdown</h5>
        <ul className="flex flex-col gap-1.5 text-sm">
          {explanation.category_breakdown.map((metric) => (
            <li key={metric.metric_name} className="flex items-center justify-between rounded-md border border-slate-200 px-2 py-1.5 dark:border-slate-800">
              <span className="text-slate-700 dark:text-slate-300">{metric.metric_name}</span>
              <span className="flex items-center gap-2">
                <span className="text-xs text-slate-500 dark:text-slate-400">{metric.score.toFixed(0)}</span>
                <PriorityBadge level={metric.severity} />
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <WeightedBarList title="Sector exposure" items={sectors} emptyMessage="No sector exposure data." valueFormat="percent" />
        <WeightedBarList title="Country exposure" items={countries} emptyMessage="No country exposure data." valueFormat="percent" />
      </div>
    </div>
  );
}
