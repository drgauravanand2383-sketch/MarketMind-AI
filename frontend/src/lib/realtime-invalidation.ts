import type { QueryClient } from "@tanstack/react-query";
import { alertsKeys } from "@/hooks/use-alerts";
import { backtestingKeys } from "@/hooks/use-backtesting";
import { explainabilityKeys } from "@/hooks/use-explainability";
import { globalMarketsKeys } from "@/hooks/use-global-markets";
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
      // v1.2 Priority 8: also refresh any open initial-analysis-status
      // poll — same "no portfolio_id on this payload" reasoning as above,
      // so the whole analysis-status prefix, not one portfolio's key.
      void queryClient.invalidateQueries({ queryKey: ["portfolio", "analysis-status"] });
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
      // v1.2 Priority 8: now genuinely published (InitialPortfolioAnalysisService
      // and, going forward, any future risk-recomputation path). `RiskAssessment`
      // carries no `portfolio_id` of its own (only `RiskAssessmentRequest`
      // does) — same "no id to scope by" situation RECOMMENDATION_GENERATED
      // above already documents, so the whole domain prefix is invalidated
      // rather than one portfolio's cache.
      void queryClient.invalidateQueries({ queryKey: ["portfolio", "risk"] });
      void queryClient.invalidateQueries({ queryKey: ["portfolio", "analysis-status"] });
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
    case "GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED":
      // The payload carries the full IntelligenceRun, but never its
      // ranked assets/reports — refetch "latest run" plus this run's own
      // cache entry so every open category panel picks up fresh data,
      // rather than trying to patch the cache from a payload that
      // doesn't carry what those panels need.
      void queryClient.invalidateQueries({ queryKey: globalMarketsKeys.latestRun() });
      void queryClient.invalidateQueries({ queryKey: globalMarketsKeys.run(event.payload.id) });
      break;
    default:
      assertNever(event);
  }
}
