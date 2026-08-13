import { create } from "zustand";

export type DecisionHistoryEntry =
  | { kind: "recommendations_generated"; id: string; portfolioId: string; requestId: string; candidateCount: number; occurredAt: string }
  | { kind: "strategy_evaluated"; id: string; requestId: string; bestStrategy: string | null; occurredAt: string }
  | { kind: "risk_loaded"; id: string; portfolioId: string; requestId: string; occurredAt: string }
  | { kind: "signals_evaluated"; id: string; resultId: string; definitionId: string; triggeredCount: number; occurredAt: string }
  | { kind: "alerts_evaluated"; id: string; generatedCount: number; suppressedCount: number; occurredAt: string }
  | { kind: "backtest_run"; id: string; runId: string; name: string; portfolioReturn: number; benchmarkReturn: number; occurredAt: string }
  | { kind: "explainability_generated"; id: string; requestId: string; recommendationResultId: string; occurredAt: string };

interface DecisionHistoryState {
  entries: DecisionHistoryEntry[];
  addEntry: (entry: DecisionHistoryEntry) => void;
  clear: () => void;
}

const MAX_ENTRIES = 20;

/**
 * This browser session's own Decision Center / Historical Analysis
 * activity only — not a durable history. None of the seven domains
 * behind these two workspaces persist a cross-session, listable
 * history: Recommendations/Risk are "latest per portfolio" only,
 * Strategy/Signals/Explainability results live in the backend's
 * in-memory `InMemoryResultStore` (cleared on restart), Backtests are
 * durably stored but keyed only by `run_id` (no "list my runs"
 * endpoint), and Alerts, while durably listed via `GET /alerts`, has no
 * concept of "which evaluate run produced these." By the same explicit
 * product decision Milestone 4 established for research/screening
 * history, this is deliberately NOT persisted to `localStorage` and
 * must be labeled in the UI as "this session."
 *
 * Milestone 6 note: the `recommendations_generated`/`strategy_evaluated`/
 * `risk_loaded` entries' `requestId` fields double as the source list
 * for the Backtesting snapshot-builder UI (`features/historical-analysis/
 * backtesting/snapshot-builder.tsx`) — there is no backend endpoint to
 * list/search existing `RecommendationResult`/`StrategyEvaluationResult`/
 * `RiskAssessment` ids, so this session's own history is the only
 * practical source (approved product decision, `docs/frontend/
 * MILESTONE_6.md`).
 */
export const useDecisionHistoryStore = create<DecisionHistoryState>()((set) => ({
  entries: [],

  addEntry: (entry) => {
    set((state) => ({ entries: [entry, ...state.entries].slice(0, MAX_ENTRIES) }));
  },
  clear: () => {
    set({ entries: [] });
  },
}));
