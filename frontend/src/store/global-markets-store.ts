import { create } from "zustand";
import type { ReportCategory } from "@/types/global-markets";

/** The five main-category tabs, plus one synthetic 6th tab that itself
 * contains 4 penny/micro-cap sub-tabs (`activePennySubTab` below) — a
 * two-level tablist, same "one active id per level" shape
 * `DecisionWorkspaceTab`/`activeTab` already establishes for the
 * Decision Center's single-level tablist. */
export type GlobalMarketsTab = "INDIA_EQUITY" | "US_EQUITY" | "CHINA_EQUITY" | "FOREX" | "CRYPTO" | "PENNY_MICROCAP";

interface GlobalMarketsUiState {
  activeTab: GlobalMarketsTab;
  activePennySubTab: ReportCategory;
  setActiveTab: (tab: GlobalMarketsTab) => void;
  setActivePennySubTab: (category: ReportCategory) => void;
}

/** Pure UI state — which tab/sub-tab is active. Never server data itself
 * (TanStack Query's job throughout, see `hooks/use-global-markets.ts`).
 * Deliberately not persisted, matching every other UI store in this app
 * (`decision-workspace-store.ts` etc.) — reopening the app to a stale
 * tab selection would be surprising, not helpful. */
export const useGlobalMarketsStore = create<GlobalMarketsUiState>()((set) => ({
  activeTab: "INDIA_EQUITY",
  activePennySubTab: "INDIA_PENNY_STOCK",

  setActiveTab: (tab) => {
    set({ activeTab: tab });
  },
  setActivePennySubTab: (category) => {
    set({ activePennySubTab: category });
  },
}));
