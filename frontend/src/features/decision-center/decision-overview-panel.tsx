import type { ReactNode } from "react";
import { Panel } from "@/components/panel";
import { PriorityBadge } from "@/components/priority-badge";
import { EmptyState } from "@/components/states/empty-state";
import { RecommendationSummaryCards } from "@/features/decision-center/recommendations/recommendation-summary-cards";
import { usePortfolioRecommendations, usePortfolioRisk } from "@/hooks/use-portfolio";
import { useDecisionWorkspaceStore, type DecisionWorkspaceTab } from "@/store/decision-workspace-store";

/** A quick-glance synthesis of whatever this portfolio already has
 * loaded — never a new backend call of its own. There is no backend
 * "overview" endpoint; this composes `usePortfolioRecommendations`/
 * `usePortfolioRisk`, the same queries the Recommendations/Risk tabs
 * themselves use (cache hits, not extra fetches). */
export function DecisionOverviewPanel({ portfolioId }: { portfolioId: string }): ReactNode {
  const recommendations = usePortfolioRecommendations(portfolioId);
  const risk = usePortfolioRisk(portfolioId);
  const setActiveTab = useDecisionWorkspaceStore((state) => state.setActiveTab);

  function goTo(tab: DecisionWorkspaceTab): void {
    setActiveTab(tab);
  }

  return (
    <div className="flex flex-col gap-6">
      <Panel title="Recommendations">
        {recommendations.isSuccess ? (
          <div className="flex flex-col gap-3">
            <RecommendationSummaryCards summary={recommendations.data.summary} />
            <button
              type="button"
              onClick={() => {
                goTo("recommendations");
              }}
              className="self-start text-sm text-brand-700 hover:underline dark:text-brand-400"
            >
              View candidates →
            </button>
          </div>
        ) : (
          <EmptyState
            title="No recommendations yet"
            description="Generate recommendations in the Recommendations tab."
            action={
              <button
                type="button"
                onClick={() => {
                  goTo("recommendations");
                }}
                className="mt-2 rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
              >
                Go to Recommendations
              </button>
            }
          />
        )}
      </Panel>

      <Panel title="Risk">
        {risk.isSuccess ? (
          <div className="flex items-center gap-3">
            <span className="text-xl font-semibold text-slate-900 dark:text-slate-100">{risk.data.overall_risk_score.toFixed(0)}</span>
            <PriorityBadge level={risk.data.overall_severity} />
            <button
              type="button"
              onClick={() => {
                goTo("risk");
              }}
              className="ml-auto text-sm text-brand-700 hover:underline dark:text-brand-400"
            >
              View full risk breakdown →
            </button>
          </div>
        ) : (
          <EmptyState
            title="No risk assessment available"
            description="No risk assessment has been generated for this portfolio yet."
            action={
              <button
                type="button"
                onClick={() => {
                  goTo("risk");
                }}
                className="mt-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Go to Risk
              </button>
            }
          />
        )}
      </Panel>

      <Panel title="Signals & Alerts">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Signals and Alerts are standalone tools not scoped to a portfolio — the backend has no portfolio concept for either
          domain. Use the Signals and Alerts tabs directly.
        </p>
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={() => {
              goTo("signals");
            }}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Go to Signals
          </button>
          <button
            type="button"
            onClick={() => {
              goTo("alerts");
            }}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Go to Alerts
          </button>
        </div>
      </Panel>
    </div>
  );
}
