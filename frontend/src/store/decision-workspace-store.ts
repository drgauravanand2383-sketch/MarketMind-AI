import { create } from "zustand";
import { usePreferencesStore } from "@/store/preferences-store";

export type DecisionWorkspaceTab = "overview" | "recommendations" | "strategy" | "risk" | "signals" | "alerts";

export interface ChartPreferences {
  /** Toggles per-point value labels on every chart in the workspace —
   * the one cross-chart preference generic enough to apply uniformly
   * (each chart's own type/axes are fixed by what it's visualizing, not
   * user-configurable). */
  showDataLabels: boolean;
}

interface DecisionWorkspaceState {
  selectedPortfolioId: string;
  activeTab: DecisionWorkspaceTab;
  /** The `RecommendationResult.request_id` currently loaded for
   * `selectedPortfolioId` — threaded explicitly into Strategy Evaluation
   * calls (`EvaluateStrategyRequest.recommendation_result_id`), since the
   * backend has no shared "decision id" linking the two domains (see
   * `docs/frontend/MILESTONE_5.md`). `null` until a `RecommendationResult`
   * has actually loaded for the selected portfolio. */
  activeRecommendationResultId: string | null;
  chartPreferences: ChartPreferences;
  setSelectedPortfolioId: (portfolioId: string) => void;
  setActiveTab: (tab: DecisionWorkspaceTab) => void;
  setActiveRecommendationResultId: (requestId: string | null) => void;
  toggleShowDataLabels: () => void;
}

/** Pure UI state for the Decision Workspace — which portfolio/tab is
 * active and which recommendation result the other tabs should thread —
 * never server data itself (that's TanStack Query's job throughout).
 * Deliberately not persisted: reopening the app to a stale portfolio
 * selection would be surprising, not helpful (same reasoning as every
 * prior milestone's UI store). */
export const useDecisionWorkspaceStore = create<DecisionWorkspaceState>()((set) => ({
  selectedPortfolioId: "",
  activeTab: "overview",
  activeRecommendationResultId: null,
  // Seeded from the user's global default chart visibility
  // (`preferences-store.ts`, Milestone 8) at store-creation time — this
  // workspace's own `toggleShowDataLabels` still overrides it per view.
  chartPreferences: { showDataLabels: usePreferencesStore.getState().charts.showDataLabels },

  setSelectedPortfolioId: (portfolioId) => {
    set({ selectedPortfolioId: portfolioId, activeRecommendationResultId: null });
  },
  setActiveTab: (tab) => {
    set({ activeTab: tab });
  },
  setActiveRecommendationResultId: (requestId) => {
    set({ activeRecommendationResultId: requestId });
  },
  toggleShowDataLabels: () => {
    set((state) => ({ chartPreferences: { ...state.chartPreferences, showDataLabels: !state.chartPreferences.showDataLabels } }));
  },
}));
