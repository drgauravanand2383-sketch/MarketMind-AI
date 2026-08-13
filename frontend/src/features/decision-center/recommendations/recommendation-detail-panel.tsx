import type { ReactNode } from "react";
import { PriorityBadge } from "@/components/priority-badge";
import { EmptyState } from "@/components/states/empty-state";
import { RecommendationTypeBadge } from "@/features/decision-center/recommendations/recommendation-type-badge";
import type { RecommendationCandidate } from "@/types/portfolio";

const SCORE_COMPONENTS: { key: keyof RecommendationCandidate; label: string }[] = [
  { key: "screening_score", label: "Screening" },
  { key: "planning_score", label: "Planning" },
  { key: "research_score", label: "Research" },
  { key: "portfolio_score", label: "Portfolio" },
  { key: "signal_score", label: "Signal" },
  { key: "alert_score", label: "Alert" },
];

/** No `GET /portfolio/recommendations/{id}` exists — this is sliced
 * client-side from the one already-fetched `RecommendationResult`, never
 * a separate fetch-by-id. */
export function RecommendationDetailPanel({ candidate }: { candidate: RecommendationCandidate | null }): ReactNode {
  if (!candidate) {
    return <EmptyState title="Select a candidate" description="Choose a row from the list to see its full detail." />;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          {candidate.ticker}
          {candidate.company_name && <span className="ml-2 text-sm font-normal text-slate-500 dark:text-slate-400">{candidate.company_name}</span>}
        </h3>
        <RecommendationTypeBadge type={candidate.recommendation} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
          <p className="text-xs text-slate-500 dark:text-slate-400">Overall score</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{candidate.overall_score.toFixed(0)}</p>
        </div>
        <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
          <p className="text-xs text-slate-500 dark:text-slate-400">Confidence</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{candidate.confidence.toFixed(0)}%</p>
        </div>
      </div>

      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Score components</h4>
        <ul className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
          {SCORE_COMPONENTS.map(({ key, label }) => {
            const value = candidate[key];
            return (
              <li key={key} className="rounded-md border border-slate-200 px-2 py-1.5 dark:border-slate-800">
                <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
                <p className="font-medium text-slate-800 dark:text-slate-200">{typeof value === "number" ? value.toFixed(0) : "—"}</p>
              </li>
            );
          })}
        </ul>
      </div>

      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Reasoning</h4>
        <p className="text-sm text-slate-700 dark:text-slate-300">{candidate.reasoning}</p>
      </div>

      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Supporting signals ({candidate.supporting_signals.length})
        </h4>
        {candidate.supporting_signals.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">No supporting signals.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {candidate.supporting_signals.map((signal) => (
              <li key={`${signal.signal_name}-${signal.timestamp}`} className="flex items-center justify-between gap-2 text-sm">
                <span className="text-slate-700 dark:text-slate-300">
                  {signal.signal_name} <span className="text-xs text-slate-500 dark:text-slate-400">({signal.category})</span>
                </span>
                <PriorityBadge level={signal.priority} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Supporting alerts ({candidate.supporting_alerts.length})
        </h4>
        {candidate.supporting_alerts.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">No supporting alerts.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {candidate.supporting_alerts.map((alert) => (
              <li key={alert.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="text-slate-700 dark:text-slate-300">{alert.reason}</span>
                <PriorityBadge level={alert.priority} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
