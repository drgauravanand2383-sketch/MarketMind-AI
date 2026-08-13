import { useEffect, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { AlertsPanel } from "@/features/decision-center/alerts/alerts-panel";
import { DecisionOverviewPanel } from "@/features/decision-center/decision-overview-panel";
import { DecisionWorkspaceTabs } from "@/features/decision-center/decision-workspace-tabs";
import { RecommendationsPanel } from "@/features/decision-center/recommendations/recommendations-panel";
import { RiskPanel } from "@/features/decision-center/risk/risk-panel";
import { SignalsPanel } from "@/features/decision-center/signals/signals-panel";
import { StrategyPanel } from "@/features/decision-center/strategy/strategy-panel";
import { useWatchlist } from "@/hooks/use-watchlists";
import { useDecisionWorkspaceStore } from "@/store/decision-workspace-store";

/**
 * "Portfolio-centered, partial sync" (approved Milestone 5 design):
 * Recommendations and Risk are auto-scoped to `portfolioId`; Strategy
 * threads whichever `RecommendationResult.request_id` the Recommendations
 * tab most recently loaded; Signals and Alerts are decoupled tools with
 * no portfolio concept on the real backend at all. There is no shared
 * backend "decision id" tying all five together — this page and
 * `useDecisionWorkspaceStore` are what make it read as one workspace.
 */
export function DecisionWorkspacePage({ portfolioId }: { portfolioId: string }): ReactNode {
  const watchlist = useWatchlist(portfolioId);
  const activeTab = useDecisionWorkspaceStore((state) => state.activeTab);
  const setSelectedPortfolioId = useDecisionWorkspaceStore((state) => state.setSelectedPortfolioId);
  const showDataLabels = useDecisionWorkspaceStore((state) => state.chartPreferences.showDataLabels);
  const toggleShowDataLabels = useDecisionWorkspaceStore((state) => state.toggleShowDataLabels);

  useEffect(() => {
    setSelectedPortfolioId(portfolioId);
  }, [portfolioId, setSelectedPortfolioId]);

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{watchlist.data?.name ?? "Decision workspace"}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Decision Center workspace for this portfolio.</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={showDataLabels} onChange={toggleShowDataLabels} />
            Show chart labels
          </label>
          <Link
            to="/decisions"
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Choose a different portfolio
          </Link>
        </div>
      </div>

      <DecisionWorkspaceTabs />

      <div role="tabpanel" id={`decision-tabpanel-${activeTab}`} aria-labelledby={`decision-tab-${activeTab}`} className="pt-4">
        {activeTab === "overview" && <DecisionOverviewPanel portfolioId={portfolioId} />}
        {activeTab === "recommendations" && <RecommendationsPanel portfolioId={portfolioId} />}
        {activeTab === "strategy" && <StrategyPanel />}
        {activeTab === "risk" && <RiskPanel portfolioId={portfolioId} />}
        {activeTab === "signals" && <SignalsPanel />}
        {activeTab === "alerts" && <AlertsPanel portfolioId={portfolioId} />}
      </div>
    </div>
  );
}
