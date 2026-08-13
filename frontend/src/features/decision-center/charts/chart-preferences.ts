import { useDecisionWorkspaceStore } from "@/store/decision-workspace-store";

/** Every Decision Center chart reads this same toggle for whether to
 * show per-bar/per-slice value labels — the one workspace-wide chart
 * preference (`docs/frontend/MILESTONE_5.md` §6). */
export function useShowDataLabels(): boolean {
  return useDecisionWorkspaceStore((state) => state.chartPreferences.showDataLabels);
}
