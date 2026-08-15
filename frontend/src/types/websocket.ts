import type { Alert } from "@/types/alerts";
import type { BacktestResult, BacktestRun } from "@/types/backtesting";
import type { DetectedChange } from "@/types/continuous-intelligence";
import type { ExplainabilityResult } from "@/types/explainability";
import type { ApplicationHealth } from "@/types/health";
import type { MarketDataRefreshResult, PortfolioIntelligenceReport, RecommendationResult, RiskAssessment } from "@/types/portfolio";
import type { StrategyEvaluationResult } from "@/types/strategy";

/**
 * Mirrors `app.api.ws` exactly (Sprint 59 —
 * `docs/architecture/WEBSOCKET_FRAMEWORK.md`). Every outbound (server ->
 * client) message has a `type` discriminant; every inbound (client ->
 * server) message has an `action` discriminant.
 */

export type EventType =
  | "ALERT_GENERATED"
  | "BACKTEST_STARTED"
  | "BACKTEST_COMPLETED"
  | "RECOMMENDATION_GENERATED"
  | "STRATEGY_EVALUATION_COMPLETED"
  | "RISK_ASSESSMENT_COMPLETED"
  | "EXPLAINABILITY_COMPLETED"
  | "HEALTH_STATUS_CHANGED"
  | "MARKET_SNAPSHOT_REFRESHED"
  | "PORTFOLIO_INTELLIGENCE_UPDATED"
  | "SIGNIFICANT_MARKET_CHANGE"
  | "SIGNIFICANT_NEWS_UPDATE"
  | "PORTFOLIO_INTELLIGENCE_CHANGED";

export interface EventMetadata {
  connection_id: string;
  delivered_at: string;
}

export interface BaseEvent<TPayload = unknown> {
  event_id: string;
  event_type: EventType;
  timestamp: string;
  correlation_id: string | null;
  payload: TPayload;
}

// --- Domain event payloads (Milestone 7) -----------------------------------------------------------

/**
 * `event_type` narrows `payload` to the real, already-typed domain
 * result the backend router constructed (never `unknown`) — the same
 * result the equivalent REST endpoint would have returned. `BACKTEST_
 * STARTED`/`BACKTEST_COMPLETED` share one backend `BacktestEvent` model
 * but carry different payload shapes (a synthetic `PENDING` `BacktestRun`
 * vs. the final `BacktestResult`) — distinguished purely by the
 * `event_type` string literal, exactly like every other event type here.
 *
 * `RISK_ASSESSMENT_COMPLETED` is modeled for completeness/exhaustiveness
 * (a real, tested backend event) but is never actually published — no
 * REST router calls `EventPublisher.publish_risk_assessment_completed()`
 * (confirmed gap, `docs/architecture/WEBSOCKET_FRAMEWORK.md` §8). It is
 * never subscribed to (`hooks/use-realtime-subscriptions.ts`) and never
 * surfaces in the Notification Center.
 *
 * Milestone 14 added `MARKET_SNAPSHOT_REFRESHED`/`PORTFOLIO_INTELLIGENCE_
 * UPDATED`; Milestone 15 added `SIGNIFICANT_MARKET_CHANGE`/
 * `SIGNIFICANT_NEWS_UPDATE`/`PORTFOLIO_INTELLIGENCE_CHANGED` — all five
 * are real, published events (unlike `RISK_ASSESSMENT_COMPLETED` above).
 */
export type DomainEvent =
  | (BaseEvent<Alert> & { event_type: "ALERT_GENERATED" })
  | (BaseEvent<BacktestRun> & { event_type: "BACKTEST_STARTED" })
  | (BaseEvent<BacktestResult> & { event_type: "BACKTEST_COMPLETED" })
  | (BaseEvent<RecommendationResult> & { event_type: "RECOMMENDATION_GENERATED" })
  | (BaseEvent<StrategyEvaluationResult> & { event_type: "STRATEGY_EVALUATION_COMPLETED" })
  | (BaseEvent<RiskAssessment> & { event_type: "RISK_ASSESSMENT_COMPLETED" })
  | (BaseEvent<ExplainabilityResult> & { event_type: "EXPLAINABILITY_COMPLETED" })
  | (BaseEvent<ApplicationHealth> & { event_type: "HEALTH_STATUS_CHANGED" })
  | (BaseEvent<MarketDataRefreshResult> & { event_type: "MARKET_SNAPSHOT_REFRESHED" })
  | (BaseEvent<PortfolioIntelligenceReport> & { event_type: "PORTFOLIO_INTELLIGENCE_UPDATED" })
  | (BaseEvent<DetectedChange> & { event_type: "SIGNIFICANT_MARKET_CHANGE" })
  | (BaseEvent<DetectedChange> & { event_type: "SIGNIFICANT_NEWS_UPDATE" })
  | (BaseEvent<DetectedChange> & { event_type: "PORTFOLIO_INTELLIGENCE_CHANGED" });

// --- Outbound (server -> client) -----------------------------------------------------------

export interface ConnectedMessage {
  type: "connected";
  connection_id: string;
}

export interface SubscriptionAckMessage {
  type: "subscribed" | "duplicate_subscription" | "unsubscribed" | "not_subscribed";
  event_types: EventType[];
  correlation_id: string | null;
}

export interface PongMessage {
  type: "pong";
}

export interface ErrorMessage {
  type: "error";
  code: "malformed_message" | "unknown_action" | "invalid_subscription" | "forbidden" | "internal_error";
  message: string;
}

export interface EventDeliveryMessage {
  type: "event";
  metadata: EventMetadata;
  event: DomainEvent;
}

export type ServerMessage = ConnectedMessage | SubscriptionAckMessage | PongMessage | ErrorMessage | EventDeliveryMessage;

// --- Inbound (client -> server) -----------------------------------------------------------

export interface SubscribeMessage {
  action: "subscribe";
  event_types: EventType[];
  correlation_id?: string;
}

export interface UnsubscribeMessage {
  action: "unsubscribe";
  event_types: EventType[];
  correlation_id?: string;
}

export interface PingMessage {
  action: "ping";
}

export type ClientMessage = SubscribeMessage | UnsubscribeMessage | PingMessage;
