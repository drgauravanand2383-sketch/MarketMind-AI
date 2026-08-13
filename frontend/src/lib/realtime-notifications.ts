import type { NotificationCenterEntry } from "@/store/realtime-notification-store";
import type { DomainEvent } from "@/types/websocket";

function signed(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/**
 * Maps one inbound `DomainEvent` to a `NotificationCenterEntry` — titles
 * reuse the exact phrasing conventions the equivalent M5/M6 mutation
 * toasts already established (`useCreateBacktest`, `useEvaluateStrategy`,
 * `useGenerateRecommendations`), so a self-triggered action's WS echo
 * reads consistently with the immediate local toast it already saw.
 * Returns `null` for `RISK_ASSESSMENT_COMPLETED` — never actually
 * published by the backend (see `types/websocket.ts`'s docstring), so it
 * never becomes a Notification Center entry.
 */
export function toNotificationEntry(event: DomainEvent): NotificationCenterEntry | null {
  switch (event.event_type) {
    case "ALERT_GENERATED":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "alerts",
        priority: event.payload.priority,
        title: `New ${event.payload.priority} alert — ${event.payload.ticker}`,
        summary: event.payload.reason,
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "alert" },
      };
    case "BACKTEST_STARTED":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "backtests",
        priority: null,
        title: "Backtest started",
        summary: "Replaying historical snapshots…",
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "backtest", runId: event.payload.request_id },
      };
    case "BACKTEST_COMPLETED":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "backtests",
        priority: null,
        title: `Backtest complete — portfolio ${signed(event.payload.portfolio_return)} vs benchmark ${signed(event.payload.benchmark_return)}`,
        summary: event.payload.summary,
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "backtest", runId: event.payload.request_id },
      };
    case "RECOMMENDATION_GENERATED":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "recommendations",
        priority: null,
        title: `Recommendations generated — ${String(event.payload.total_candidates)} candidates scored`,
        summary: `${String(event.payload.summary.strong_buy)} strong buy, ${String(event.payload.summary.buy)} buy, ${String(event.payload.summary.watch)} watch.`,
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "recommendation" },
      };
    case "STRATEGY_EVALUATION_COMPLETED":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "strategy",
        priority: null,
        title: event.payload.best_strategy
          ? `Strategy evaluation complete — best match: ${event.payload.best_strategy}`
          : "Strategy evaluation complete",
        summary: `Overall alignment ${event.payload.overall_alignment.toFixed(0)}.`,
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "strategy" },
      };
    case "EXPLAINABILITY_COMPLETED":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "explainability",
        priority: null,
        title: "Explainability report generated",
        summary: event.payload.overall_summary,
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "explainability", requestId: event.payload.request_id },
      };
    case "HEALTH_STATUS_CHANGED":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "health",
        priority: event.payload.state === "UNHEALTHY" ? "CRITICAL" : event.payload.state === "DEGRADED" ? "MODERATE" : null,
        title: `System health: ${event.payload.state}`,
        summary: event.payload.summary,
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "health" },
      };
    case "RISK_ASSESSMENT_COMPLETED":
      return null;
  }
}
