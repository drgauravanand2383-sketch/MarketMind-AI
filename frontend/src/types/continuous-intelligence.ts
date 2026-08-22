/**
 * Mirrors `app.services.continuous_intelligence.models` (Milestone 15).
 * `DetectedChange` is the single payload shape for all three proactive
 * WS event types (`SIGNIFICANT_MARKET_CHANGE`/`SIGNIFICANT_NEWS_UPDATE`/
 * `PORTFOLIO_INTELLIGENCE_CHANGED`) — never recomputed client-side, the
 * exact object the backend already classified and published.
 */

export type ChangeDomain = "MARKET" | "NEWS" | "RISK" | "RECOMMENDATION" | "STRATEGY" | "SIGNAL";

/** A new 5-tier scale distinct from `PriorityLevel` (which has no
 * `INFO`) — see `app.services.continuous_intelligence.models`'s own
 * docstring for why. Every existing severity/priority enum maps into
 * this one deterministically backend-side; the frontend never needs to
 * re-derive it. */
export type ChangePriority = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface DetectedChange {
  fingerprint: string;
  domain: ChangeDomain;
  entity_id: string;
  label: string;
  priority: ChangePriority;
  summary: string;
  previous_value: string | null;
  current_value: string | null;
  portfolio_id: string | null;
  /** v1.2 Priority 1: the portfolio-agnostic identity of the underlying
   * real-world event — stable across every per-portfolio copy of one
   * change, unlike `fingerprint` (which is deliberately unique per
   * portfolio). `null` only for a change published before this field
   * existed. */
  event_fingerprint?: string | null;
  /** v1.2 Priority 2: every portfolio this event was found impacted for
   * and which independently survived its own suppression check —
   * present so a single received event is self-sufficient to show
   * "Affected: N portfolios" without waiting for sibling events. Empty
   * for a portfolio-agnostic change or one already scoped to exactly
   * one portfolio at detection time (Risk/Recommendation/Strategy). */
  impacted_portfolio_ids?: string[];
  detected_at: string;
}
