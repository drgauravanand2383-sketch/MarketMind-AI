import { create } from "zustand";
import type { ReportCategory } from "@/types/global-markets";

/** A synthetic "Top Picks" digest tab, then the five main-category tabs,
 * then one synthetic tab that itself contains 4 penny/micro-cap sub-tabs
 * (`activePennySubTab` below) — a two-level tablist, same "one active id
 * per level" shape `DecisionWorkspaceTab`/`activeTab` already establishes
 * for the Decision Center's single-level tablist. `TOP_PICKS` and
 * `PENNY_MICROCAP` are frontend groupings, not backend categories. */
export type GlobalMarketsTab =
  | "TOP_PICKS"
  | "INDIA_EQUITY"
  | "US_EQUITY"
  | "CHINA_EQUITY"
  | "FOREX"
  | "CRYPTO"
  | "PENNY_MICROCAP";

interface GlobalMarketsUiState {
  activeTab: GlobalMarketsTab;
  activePennySubTab: ReportCategory;
  /** `null` means "the latest run" (the default, and the only state
   * before the historical run picker was added) — a specific run id
   * once the user picks a past date from `RunPicker`. */
  selectedRunId: string | null;
  setActiveTab: (tab: GlobalMarketsTab) => void;
  setActivePennySubTab: (category: ReportCategory) => void;
  setSelectedRunId: (runId: string | null) => void;
}

/** Pure UI state — which tab/sub-tab is active. Never server data itself
 * (TanStack Query's job throughout, see `hooks/use-global-markets.ts`).
 * Deliberately not persisted, matching every other UI store in this app
 * (`decision-workspace-store.ts` etc.) — reopening the app to a stale
 * tab selection would be surprising, not helpful. */
export const useGlobalMarketsStore = create<GlobalMarketsUiState>()((set) => ({
  activeTab: "TOP_PICKS",
  activePennySubTab: "INDIA_PENNY_STOCK",
  selectedRunId: null,

  setActiveTab: (tab) => {
    set({ activeTab: tab });
  },
  setActivePennySubTab: (category) => {
    set({ activePennySubTab: category });
  },
  setSelectedRunId: (runId) => {
    set({ selectedRunId: runId });
  },
}));
