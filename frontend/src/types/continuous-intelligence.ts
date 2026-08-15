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
  detected_at: string;
}
