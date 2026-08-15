import { describe, expect, it, vi } from "vitest";
import type { QueryClient } from "@tanstack/react-query";
import { invalidateForEvent } from "@/lib/realtime-invalidation";
import { buildDomainEvent } from "@/test/mock-websocket";
import { testApplicationHealth, buildAlert, buildBacktestResult, buildBacktestRun, buildDetectedChange, buildExplainabilityResult, buildMarketDataRefreshResult, buildRecommendationResult, buildRiskAssessment, buildStrategyEvaluationResult, testPortfolioIntelligenceReport } from "@/test/msw/fixtures";

function fakeQueryClient(): { invalidateQueries: ReturnType<typeof vi.fn>; asQueryClient: QueryClient } {
  const invalidateQueries = vi.fn();
  return { invalidateQueries, asQueryClient: { invalidateQueries } as unknown as QueryClient };
}

describe("invalidateForEvent", () => {
  it("invalidates the alerts list on ALERT_GENERATED", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("ALERT_GENERATED", buildAlert()));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["alerts", "list"] });
  });

  it("surgically invalidates the run and result queries on BACKTEST_STARTED/COMPLETED using the payload's request_id", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("BACKTEST_STARTED", buildBacktestRun({ request_id: "run-42" })));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["backtests", "run", "run-42"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["backtests", "results", "run-42"] });

    invalidateQueries.mockClear();
    invalidateForEvent(asQueryClient, buildDomainEvent("BACKTEST_COMPLETED", buildBacktestResult({ request_id: "run-42" })));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["backtests", "run", "run-42"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["backtests", "results", "run-42"] });
  });

  it("invalidates the whole portfolio-recommendations prefix on RECOMMENDATION_GENERATED (no portfolio_id on the payload)", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("RECOMMENDATION_GENERATED", buildRecommendationResult()));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["portfolio", "recommendations"] });
  });

  it("surgically invalidates the strategy result on STRATEGY_EVALUATION_COMPLETED", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("STRATEGY_EVALUATION_COMPLETED", buildStrategyEvaluationResult({ request_id: "eval-9" })));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["strategies", "results", "eval-9"] });
  });

  it("surgically invalidates the explainability result on EXPLAINABILITY_COMPLETED", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("EXPLAINABILITY_COMPLETED", buildExplainabilityResult({ request_id: "exp-7" })));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["explainability", "results", "exp-7"] });
  });

  it("invalidates system health and readiness on HEALTH_STATUS_CHANGED", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("HEALTH_STATUS_CHANGED", testApplicationHealth));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["system", "health"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["system", "ready"] });
  });

  it("is a no-op for RISK_ASSESSMENT_COMPLETED (never actually published)", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("RISK_ASSESSMENT_COMPLETED", buildRiskAssessment()));
    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("is a no-op for MARKET_SNAPSHOT_REFRESHED (portfolio-agnostic, no cache to target)", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("MARKET_SNAPSHOT_REFRESHED", buildMarketDataRefreshResult()));
    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("invalidates the portfolio intelligence cache on PORTFOLIO_INTELLIGENCE_UPDATED", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("PORTFOLIO_INTELLIGENCE_UPDATED", testPortfolioIntelligenceReport, { correlation_id: "wl-1" }));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["portfolio", "intelligence", "wl-1"] });
  });

  it("invalidates the portfolio intelligence cache on SIGNIFICANT_MARKET_CHANGE when portfolio-scoped", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", buildDetectedChange({ portfolio_id: "wl-1" })));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["portfolio", "intelligence", "wl-1"] });
  });

  it("is a no-op for SIGNIFICANT_NEWS_UPDATE when no portfolio is impacted", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("SIGNIFICANT_NEWS_UPDATE", buildDetectedChange({ portfolio_id: null })));
    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("invalidates the risk cache on PORTFOLIO_INTELLIGENCE_CHANGED with domain RISK", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("PORTFOLIO_INTELLIGENCE_CHANGED", buildDetectedChange({ domain: "RISK", portfolio_id: "wl-1" })));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["portfolio", "risk", "wl-1"] });
  });

  it("invalidates the recommendations cache on PORTFOLIO_INTELLIGENCE_CHANGED with domain RECOMMENDATION", () => {
    const { invalidateQueries, asQueryClient } = fakeQueryClient();
    invalidateForEvent(asQueryClient, buildDomainEvent("PORTFOLIO_INTELLIGENCE_CHANGED", buildDetectedChange({ domain: "RECOMMENDATION", portfolio_id: "wl-1" })));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["portfolio", "recommendations", "wl-1"] });
  });
});
