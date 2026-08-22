import type { PriorityLevel } from "@/components/priority-badge";
import type { ChangePriority } from "@/types/continuous-intelligence";
import type { NotificationCenterEntry } from "@/store/realtime-notification-store";
import type { DomainEvent } from "@/types/websocket";

function signed(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/** v1.2 Priority 2: `undefined` unless the event genuinely impacted more
 * than one portfolio — a single-portfolio (or portfolio-agnostic) change
 * shows no "Affected" line at all, matching pre-v1.2 behavior exactly. */
function affectedPortfolioSuffix(count: number | undefined): string {
  return count !== undefined && count > 1 ? ` Affected: ${String(count)} portfolios.` : "";
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
        // v1.2 Priority 1: company name (when known) alongside the
        // ticker — `event.payload.reason` (the summary below) is now a
        // real, signal-specific explanation rather than a generic
        // sentence identical across every alert, so the title only needs
        // to identify *what*, not restate *why*.
        title: event.payload.company_name
          ? `New ${event.payload.priority} alert — ${event.payload.company_name} (${event.payload.ticker})`
          : `New ${event.payload.priority} alert — ${event.payload.ticker}`,
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
    case "SIGNIFICANT_MARKET_CHANGE": {
      const count = event.payload.impacted_portfolio_ids?.length;
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "market",
        priority: toPriorityLevel(event.payload.priority),
        title: `${event.payload.label}: significant market move`,
        summary: event.payload.summary + affectedPortfolioSuffix(count),
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "market", portfolioId: event.payload.portfolio_id },
        ...(event.payload.event_fingerprint != null && { groupKey: event.payload.event_fingerprint }),
        ...(count !== undefined && count > 1 && { affectedPortfolioCount: count }),
      };
    }
    case "SIGNIFICANT_NEWS_UPDATE": {
      const count = event.payload.impacted_portfolio_ids?.length;
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "news",
        priority: toPriorityLevel(event.payload.priority),
        title: `${event.payload.label}: new evidence`,
        summary: event.payload.summary + affectedPortfolioSuffix(count),
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "news", portfolioId: event.payload.portfolio_id },
        ...(event.payload.event_fingerprint != null && { groupKey: event.payload.event_fingerprint }),
        ...(count !== undefined && count > 1 && { affectedPortfolioCount: count }),
      };
    }
    case "PORTFOLIO_INTELLIGENCE_CHANGED": {
      const count = event.payload.impacted_portfolio_ids?.length;
      const priority = toPriorityLevel(event.payload.priority);
      return {
        id: event.event_id,
        eventType: event.event_type,
        domain: "decisions",
        priority,
        title: `${event.payload.label}: ${event.payload.domain.toLowerCase()} changed`,
        summary: event.payload.summary + affectedPortfolioSuffix(count),
        occurredAt: event.timestamp,
        read: false,
        entityRef: { kind: "decision", portfolioId: event.payload.portfolio_id },
        ...(event.payload.event_fingerprint != null && { groupKey: event.payload.event_fingerprint }),
        ...(count !== undefined && count > 1 && { affectedPortfolioCount: count }),
        // v1.2 Priority 3: only RISK/RECOMMENDATION/STRATEGY/SIGNAL ever
        // reach this event type, and only when a real portfolio is
        // known - both already guaranteed by the branch this object
        // literal is in, so this is always safe to build.
        ...(event.payload.portfolio_id != null && {
          pendingDigestChange: {
            eventFingerprint: event.payload.event_fingerprint ?? event.payload.fingerprint,
            domain: event.payload.domain,
            label: event.payload.label,
            previousValue: event.payload.previous_value,
            currentValue: event.payload.current_value,
            priority,
            summary: event.payload.summary,
            occurredAt: event.timestamp,
          },
        }),
      };
    }
  }
}
