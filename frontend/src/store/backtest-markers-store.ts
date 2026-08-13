import { create } from "zustand";

export interface BacktestMarker {
  timestamp: string;
  recommendationResultId: string;
  strategyEvaluationId?: string;
  riskAssessmentId?: string;
}

interface BacktestMarkersState {
  markersByRunId: Record<string, BacktestMarker[]>;
  setMarkersForRun: (runId: string, markers: BacktestMarker[]) => void;
}

/**
 * Client-side-only reconstruction of "which recommendation/strategy/risk
 * result fed each backtest period" — approved product decision,
 * `docs/frontend/MILESTONE_6.md`. `BacktestPeriod` (the backend's own
 * per-period result) carries no back-reference to the
 * `HistoricalSnapshot` that produced it, and no GET endpoint ever
 * returns the original snapshot list — the mapping only exists at the
 * moment the frontend itself submits `POST /backtests`. This store
 * captures it then, keyed by the resulting `run_id`, so the timeline can
 * render recommendation markers **only for backtests created in the
 * current session** — a run loaded by id from a previous session (or
 * after a page reload) will have no entry here, and the timeline must
 * render without markers in that case rather than fabricate one.
 * Deliberately not persisted, for the same reason `session-activity-
 * store.ts` (Milestone 4) and `decision-history-store.ts` (Milestone 5)
 * aren't.
 */
export const useBacktestMarkersStore = create<BacktestMarkersState>()((set) => ({
  markersByRunId: {},

  setMarkersForRun: (runId, markers) => {
    set((state) => ({ markersByRunId: { ...state.markersByRunId, [runId]: markers } }));
  },
}));
