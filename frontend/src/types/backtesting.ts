/**
 * Mirrors `app.backtesting.models` field-for-field (verified against the
 * actual backend source, Frontend Milestone 6). The Backtesting Framework
 * never fetches live market data, executes a trade, or models a real P&L
 * — `BacktestPeriod.portfolio_value` is a deterministic *proxy* derived
 * only from already-computed 0-100 component scores, never a real
 * valuation. `{run_id}` (used in both GET endpoints) is the
 * `BacktestRequest.id` throughout — `BacktestRun`/`BacktestResult` have
 * no id of their own.
 *
 * `HistoricalSnapshot.benchmark_value` is the one value nowhere in this
 * pipeline can derive — it is accepted as directly caller-supplied, the
 * same resolution `CandidateEvidence.planning_score` (Milestone 5) used.
 * `HistoricalSnapshot`s carry references (`recommendation_result_id`,
 * etc.) to already-persisted results; there is no backend endpoint to
 * list/search those results to build a snapshot from — Milestone 6's
 * snapshot-builder UI sources them from this session's own Decision
 * Center activity (`@/store/decision-history-store`) instead.
 */

export type ReplayMode = "DAILY" | "WEEKLY" | "MONTHLY" | "CUSTOM";

export const REPLAY_MODES: ReplayMode[] = ["DAILY", "WEEKLY", "MONTHLY", "CUSTOM"];

export type BacktestStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";

export interface HistoricalSnapshot {
  timestamp: string;
  recommendation_result_id: string;
  strategy_evaluation_id?: string | null;
  risk_assessment_id?: string | null;
  benchmark_value?: number | null;
}

/** All return/drawdown/win-rate values below are plain percentage
 * numbers (e.g. `12.34` means 12.34%), never a 0-1 fraction — confirmed
 * against `app/backtesting/engine.py`'s own arithmetic. */
export interface BacktestPeriod {
  timestamp: string;
  portfolio_value: number;
  benchmark_value: number | null;
  return_percent: number;
  notes: string;
}

export interface BacktestRun {
  request_id: string;
  started_at: string;
  completed_at: string | null;
  status: BacktestStatus;
  processed_snapshots: number;
  /** The periods table — also the only source for the historical timeline. */
  results: BacktestPeriod[];
}

export interface BacktestResult {
  request_id: string;
  portfolio_return: number;
  benchmark_return: number;
  excess_return: number;
  max_drawdown: number;
  win_rate: number;
  total_periods: number;
  successful_periods: number;
  failed_periods: number;
  summary: string;
  generated_at: string;
}

export interface CreateBacktestRequest {
  name: string;
  description?: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  benchmark: string;
  strategy_ids?: string[];
  replay_mode?: ReplayMode;
  snapshots?: HistoricalSnapshot[];
}
