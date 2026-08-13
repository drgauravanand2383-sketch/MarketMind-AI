import { useHistoricalAnalysisUiStore } from "@/store/historical-analysis-ui-store";

/** Every Historical Analysis chart reads this same toggle for whether to
 * show per-bar/per-slice value labels — mirrors the identical Decision
 * Center preference from Milestone 5, scoped to this workspace's own store. */
export function useShowDataLabels(): boolean {
  return useHistoricalAnalysisUiStore((state) => state.chartPreferences.showDataLabels);
}
