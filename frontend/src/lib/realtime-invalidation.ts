import type { QueryClient } from "@tanstack/react-query";
import { alertsKeys } from "@/hooks/use-alerts";
import { backtestingKeys } from "@/hooks/use-backtesting";
import { explainabilityKeys } from "@/hooks/use-explainability";
import { portfolioKeys } from "@/hooks/use-portfolio";
import { strategyKeys } from "@/hooks/use-strategy";
import type { DomainEvent } from "@/types/websocket";

function assertNever(value: never): never {
  throw new Error(`Unhandled event type: ${JSON.stringify(value)}`);
}

/**
 * "Refresh only impacted data. Do not refetch unrelated pages" (Milestone
 * 7 spec) — one exhaustive switch over `DomainEvent["event_type"]`, so a
 * future 9th backend event type fails the build here until handled
 * (`no any`/strict-TS project rule). Backtest/Strategy/Explainability
 * events carry the exact id their query hooks already key on
 * (`request_id`) and are invalidated surgically; Alert/Recommendation
 * events carry no id their own list/portfolio-scoped query could be
 * targeted by (no list params, no `portfolio_id` on `RecommendationResult`
 * — confirmed against the real types), so the whole domain-level prefix
 * is invalidated instead — still scoped to that one domain, never
 * touching an unrelated one.
 */
export function invalidateForEvent(queryClient: QueryClient, event: DomainEvent): void {
  switch (event.event_type) {
    case "ALERT_GENERATED":
      void queryClient.invalidateQueries({ queryKey: alertsKeys.lists() });
      break;
    case "BACKTEST_STARTED":
    case "BACKTEST_COMPLETED": {
      const runId = event.payload.request_id;
      void queryClient.invalidateQueries({ queryKey: backtestingKeys.run(runId) });
      void queryClient.invalidateQueries({ queryKey: backtestingKeys.result(runId) });
      break;
    }
    case "RECOMMENDATION_GENERATED":
      void queryClient.invalidateQueries({ queryKey: ["portfolio", "recommendations"] });
      break;
    case "STRATEGY_EVALUATION_COMPLETED":
      void queryClient.invalidateQueries({ queryKey: strategyKeys.result(event.payload.request_id) });
      break;
    case "EXPLAINABILITY_COMPLETED":
      void queryClient.invalidateQueries({ queryKey: explainabilityKeys.result(event.payload.request_id) });
      break;
    case "HEALTH_STATUS_CHANGED":
      void queryClient.invalidateQueries({ queryKey: ["system", "health"] });
      void queryClient.invalidateQueries({ queryKey: ["system", "ready"] });
      break;
    case "RISK_ASSESSMENT_COMPLETED":
      // Never actually published — see docs/architecture/WEBSOCKET_FRAMEWORK.md §8.
      break;
    case "MARKET_SNAPSHOT_REFRESHED":
      // Portfolio-agnostic (every canonical entity at once, Milestone 14)
      // — no single portfolio_id to scope to; the Notification Center is
      // this event's only surface, no query cache to invalidate.
      break;
    case "PORTFOLIO_INTELLIGENCE_UPDATED":
      void queryClient.invalidateQueries({ queryKey: portfolioKeys.intelligence(event.correlation_id ?? "") });
      break;
    case "SIGNIFICANT_MARKET_CHANGE":
    case "SIGNIFICANT_NEWS_UPDATE":
      // Both carry a market/news-derived DetectedChange (Milestone 15) —
      // only invalidate the one portfolio-scoped cache that actually
      // surfaces this data (the intelligence report's attached market
      // snapshot) when Decision Impact determined a portfolio to scope to.
      if (event.payload.portfolio_id) {
        void queryClient.invalidateQueries({ queryKey: portfolioKeys.intelligence(event.payload.portfolio_id) });
      }
      break;
    case "PORTFOLIO_INTELLIGENCE_CHANGED": {
      const { portfolio_id, domain } = event.payload;
      if (!portfolio_id) break;
      if (domain === "RISK") void queryClient.invalidateQueries({ queryKey: portfolioKeys.risk(portfolio_id) });
      else if (domain === "RECOMMENDATION") void queryClient.invalidateQueries({ queryKey: portfolioKeys.recommendations(portfolio_id) });
      // STRATEGY/SIGNAL: no existing portfolio-scoped query cache to target
      // (`strategyKeys` is keyed by evaluation request_id, not portfolio_id)
      // — the Notification Center still surfaces the change either way.
      break;
    }
    default:
      assertNever(event);
  }
}
