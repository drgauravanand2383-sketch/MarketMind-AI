import type { PriorityLevel } from "@/components/priority-badge";
import type { ChangePriority } from "@/types/continuous-intelligence";
import type { NotificationCenterEntry } from "@/store/realtime-notification-store";
import type { DomainEvent } from "@/types/websocket";

function signed(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/** `ChangePriority` (Milestone 15) has one tier — `INFO` — with no
 * `PriorityLevel` equivalent; every other tier passes through directly. */
function toPriorityLevel(priority: ChangePriority): PriorityLevel | null {
  return priority === "INFO" ? null : priority;
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
    case "MARKET_SNAPSHOT_REFRESHED":
      // A scheduled refresh completing is not itself meaningful (Milestone
      // 15's own "do not emit an event simply because a scheduler ran"
      // principle, applied retroactively to this Milestone 14 event) —
      // SIGNIFICANT_MARKET_CHANGE below is the "worth telling the user
      // about" version. Cache invalidation still happens either way.
      return null;
    case "PORTFOLIO_INTELLIGENCE_UPDATED":
      // Fires on every GET /portfolio/intelligence — a fetch, not a
      // proactive notice. PORTFOLIO_INTELLIGENCE_CHANGED below is the
      // proactive equivalent.
      return null;
    case "SIGNIFICANT_MARKET_CHANGE":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "market",
        priority: toPriorityLevel(event.payload.priority),
        title: `${event.payload.label}: significant market move`,
        summary: event.payload.summary,
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "market", portfolioId: event.payload.portfolio_id },
      };
    case "SIGNIFICANT_NEWS_UPDATE":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "news",
        priority: toPriorityLevel(event.payload.priority),
        title: `${event.payload.label}: new evidence`,
        summary: event.payload.summary,
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "news", portfolioId: event.payload.portfolio_id },
      };
    case "PORTFOLIO_INTELLIGENCE_CHANGED":
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "decisions",
        priority: toPriorityLevel(event.payload.priority),
        title: `${event.payload.label}: ${event.payload.domain.toLowerCase()} changed`,
        summary: event.payload.summary,
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "decision", portfolioId: event.payload.portfolio_id },
      };
  }
}
