import { create } from "zustand";

const MAX_RESEARCH_COMPARE = 2;
const MAX_SCREENING_COMPARE = 4;
const MAX_BACKTEST_COMPARE = 2;
const MAX_EXPLAINABILITY_COMPARE = 2;

interface ComparisonState {
  researchRequestIds: string[];
  screeningResultIds: string[];
  backtestRunIds: string[];
  explainabilityRequestIds: string[];
  toggleResearch: (requestId: string) => void;
  toggleScreeningResult: (resultId: string) => void;
  toggleBacktestRun: (runId: string) => void;
  toggleExplainabilityResult: (requestId: string) => void;
  clearResearch: () => void;
  clearScreeningResults: () => void;
  clearBacktestRuns: () => void;
  clearExplainabilityResults: () => void;
}

/** Pure UI selection state for the comparison views — which already-
 * fetched reports/results the user has picked to compare side by side.
 * Never fetches or computes anything itself; the comparison pages read
 * these ids and pull the actual data from TanStack Query's cache. Newest
 * selection bumps the oldest once the cap is reached, rather than
 * silently refusing further picks. */
export const useComparisonStore = create<ComparisonState>()((set, get) => ({
  researchRequestIds: [],
  screeningResultIds: [],
  backtestRunIds: [],
  explainabilityRequestIds: [],

  toggleResearch: (requestId) => {
    const current = get().researchRequestIds;
    if (current.includes(requestId)) {
      set({ researchRequestIds: current.filter((id) => id !== requestId) });
      return;
    }
    const next = [...current, requestId];
    set({ researchRequestIds: next.length > MAX_RESEARCH_COMPARE ? next.slice(next.length - MAX_RESEARCH_COMPARE) : next });
  },

  toggleScreeningResult: (resultId) => {
    const current = get().screeningResultIds;
    if (current.includes(resultId)) {
      set({ screeningResultIds: current.filter((id) => id !== resultId) });
      return;
    }
    const next = [...current, resultId];
    set({
      screeningResultIds:
        next.length > MAX_SCREENING_COMPARE ? next.slice(next.length - MAX_SCREENING_COMPARE) : next,
    });
  },

  toggleBacktestRun: (runId) => {
    const current = get().backtestRunIds;
    if (current.includes(runId)) {
      set({ backtestRunIds: current.filter((id) => id !== runId) });
      return;
    }
    const next = [...current, runId];
    set({ backtestRunIds: next.length > MAX_BACKTEST_COMPARE ? next.slice(next.length - MAX_BACKTEST_COMPARE) : next });
  },

  toggleExplainabilityResult: (requestId) => {
    const current = get().explainabilityRequestIds;
    if (current.includes(requestId)) {
      set({ explainabilityRequestIds: current.filter((id) => id !== requestId) });
      return;
    }
    const next = [...current, requestId];
    set({
      explainabilityRequestIds:
        next.length > MAX_EXPLAINABILITY_COMPARE ? next.slice(next.length - MAX_EXPLAINABILITY_COMPARE) : next,
    });
  },

  clearResearch: () => {
    set({ researchRequestIds: [] });
  },
  clearScreeningResults: () => {
    set({ screeningResultIds: [] });
  },
  clearBacktestRuns: () => {
    set({ backtestRunIds: [] });
  },
  clearExplainabilityResults: () => {
    set({ explainabilityRequestIds: [] });
  },
}));
