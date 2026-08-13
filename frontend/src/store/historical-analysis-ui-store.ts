import { create } from "zustand";
import { usePreferencesStore } from "@/store/preferences-store";

export type TimelineMetric = "portfolio" | "benchmark" | "both";

interface HistoricalAnalysisUiState {
  /** Which value line(s) the interactive timeline plots. */
  timelineMetric: TimelineMetric;
  setTimelineMetric: (metric: TimelineMetric) => void;
  /** Toggles per-point value labels on every Historical Analysis chart —
   * the same single, workspace-wide preference Milestone 5 established
   * for the Decision Center, scoped separately here since this is a
   * different workspace/store. */
  chartPreferences: { showDataLabels: boolean };
  toggleShowDataLabels: () => void;
  /** Client-side-only filter over the periods table (`GET /backtests/{id}`
   * returns every period in one unpaginated array, no server-side
   * filter/sort params) — mirrors the reasoned client-side exception
   * Milestone 4/5 established for screening/signal results. */
  periodsSearch: string;
  setPeriodsSearch: (value: string) => void;
}

/** Pure UI state for the Historical Analysis Center — timeline display
 * preferences, chart preferences, and the periods-table filter. Never
 * server data itself. Not persisted: reopening the app to a stale
 * filter/preference would be surprising, not helpful (same reasoning as
 * every prior milestone's UI store). */
export const useHistoricalAnalysisUiStore = create<HistoricalAnalysisUiState>()((set) => ({
  timelineMetric: "both",
  setTimelineMetric: (metric) => {
    set({ timelineMetric: metric });
  },
  // Seeded from the user's global default chart visibility
  // (`preferences-store.ts`, Milestone 8) at store-creation time.
  chartPreferences: { showDataLabels: usePreferencesStore.getState().charts.showDataLabels },
  toggleShowDataLabels: () => {
    set((state) => ({ chartPreferences: { showDataLabels: !state.chartPreferences.showDataLabels } }));
  },
  periodsSearch: "",
  setPeriodsSearch: (value) => {
    set({ periodsSearch: value });
  },
}));
