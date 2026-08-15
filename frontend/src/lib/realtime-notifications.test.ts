import { describe, expect, it } from "vitest";
import { toNotificationEntry } from "@/lib/realtime-notifications";
import { buildDomainEvent } from "@/test/mock-websocket";
import {
  buildAlert,
  buildBacktestResult,
  buildBacktestRun,
  buildDetectedChange,
  buildExplainabilityResult,
  buildMarketDataRefreshResult,
  buildRecommendationResult,
  buildRiskAssessment,
  buildStrategyEvaluationResult,
  testApplicationHealth,
  testPortfolioIntelligenceReport,
} from "@/test/msw/fixtures";

describe("toNotificationEntry", () => {
  it("maps ALERT_GENERATED to an alerts-domain entry with the alert's own priority and no deep link", () => {
    const entry = toNotificationEntry(buildDomainEvent("ALERT_GENERATED", buildAlert({ priority: "CRITICAL", ticker: "AAPL" })));
    expect(entry).toMatchObject({ domain: "alerts", priority: "CRITICAL", entityRef: { kind: "alert" } });
    expect(entry?.title).toContain("AAPL");
  });

  it("maps BACKTEST_STARTED/COMPLETED to a backtests-domain entry linking to the run id", () => {
    const started = toNotificationEntry(buildDomainEvent("BACKTEST_STARTED", buildBacktestRun({ request_id: "run-1" })));
    expect(started).toMatchObject({ domain: "backtests", entityRef: { kind: "backtest", runId: "run-1" } });

    const completed = toNotificationEntry(buildDomainEvent("BACKTEST_COMPLETED", buildBacktestResult({ request_id: "run-1", portfolio_return: 4, benchmark_return: 1.5 })));
    expect(completed).toMatchObject({ domain: "backtests", entityRef: { kind: "backtest", runId: "run-1" } });
    expect(completed?.title).toContain("+4.00%");
  });

  it("maps RECOMMENDATION_GENERATED to a recommendations-domain entry with no deep link", () => {
    const entry = toNotificationEntry(buildDomainEvent("RECOMMENDATION_GENERATED", buildRecommendationResult({ total_candidates: 5 })));
    expect(entry).toMatchObject({ domain: "recommendations", priority: null, entityRef: { kind: "recommendation" } });
    expect(entry?.title).toContain("5");
  });

  it("maps STRATEGY_EVALUATION_COMPLETED to a strategy-domain entry with no deep link", () => {
    const entry = toNotificationEntry(buildDomainEvent("STRATEGY_EVALUATION_COMPLETED", buildStrategyEvaluationResult({ best_strategy: "Momentum Growth" })));
    expect(entry).toMatchObject({ domain: "strategy", entityRef: { kind: "strategy" } });
    expect(entry?.title).toContain("Momentum Growth");
  });

  it("maps EXPLAINABILITY_COMPLETED to an explainability-domain entry linking to the request id", () => {
    const entry = toNotificationEntry(buildDomainEvent("EXPLAINABILITY_COMPLETED", buildExplainabilityResult({ request_id: "exp-1" })));
    expect(entry).toMatchObject({ domain: "explainability", entityRef: { kind: "explainability", requestId: "exp-1" } });
  });

  it("derives HEALTH_STATUS_CHANGED priority from ApplicationHealth.state", () => {
    expect(toNotificationEntry(buildDomainEvent("HEALTH_STATUS_CHANGED", { ...testApplicationHealth, state: "HEALTHY" }))?.priority).toBeNull();
    expect(toNotificationEntry(buildDomainEvent("HEALTH_STATUS_CHANGED", { ...testApplicationHealth, state: "DEGRADED" }))?.priority).toBe("MODERATE");
    expect(toNotificationEntry(buildDomainEvent("HEALTH_STATUS_CHANGED", { ...testApplicationHealth, state: "UNHEALTHY" }))?.priority).toBe("CRITICAL");
  });

  it("returns null for RISK_ASSESSMENT_COMPLETED (never actually published)", () => {
    expect(toNotificationEntry(buildDomainEvent("RISK_ASSESSMENT_COMPLETED", buildRiskAssessment()))).toBeNull();
  });

  it("returns null for MARKET_SNAPSHOT_REFRESHED (a scheduled refresh completing is not itself meaningful)", () => {
    expect(toNotificationEntry(buildDomainEvent("MARKET_SNAPSHOT_REFRESHED", buildMarketDataRefreshResult()))).toBeNull();
  });

  it("returns null for PORTFOLIO_INTELLIGENCE_UPDATED (a fetch, not a proactive notice)", () => {
    expect(toNotificationEntry(buildDomainEvent("PORTFOLIO_INTELLIGENCE_UPDATED", testPortfolioIntelligenceReport))).toBeNull();
  });

  it("maps SIGNIFICANT_MARKET_CHANGE to a market-domain entry carrying the portfolio_id deep link", () => {
    const change = buildDetectedChange({ domain: "MARKET", label: "Dell", priority: "CRITICAL", portfolio_id: "wl-1" });
    const entry = toNotificationEntry(buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", change));
    expect(entry).toMatchObject({ domain: "market", priority: "CRITICAL", entityRef: { kind: "market", portfolioId: "wl-1" } });
    expect(entry?.title).toContain("Dell");
  });

  it("maps SIGNIFICANT_NEWS_UPDATE to a news-domain entry", () => {
    const change = buildDetectedChange({ domain: "NEWS", label: "Dell", priority: "MEDIUM", portfolio_id: null });
    const entry = toNotificationEntry(buildDomainEvent("SIGNIFICANT_NEWS_UPDATE", change));
    expect(entry).toMatchObject({ domain: "news", priority: "MEDIUM", entityRef: { kind: "news", portfolioId: null } });
  });

  it("maps PORTFOLIO_INTELLIGENCE_CHANGED to a decisions-domain entry", () => {
    const change = buildDetectedChange({ domain: "RISK", label: "My Portfolio", priority: "HIGH", portfolio_id: "wl-1" });
    const entry = toNotificationEntry(buildDomainEvent("PORTFOLIO_INTELLIGENCE_CHANGED", change));
    expect(entry).toMatchObject({ domain: "decisions", priority: "HIGH", entityRef: { kind: "decision", portfolioId: "wl-1" } });
  });

  it("maps ChangePriority INFO to a null PriorityLevel (no equivalent tier)", () => {
    const change = buildDetectedChange({ priority: "INFO" });
    const entry = toNotificationEntry(buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", change));
    expect(entry?.priority).toBeNull();
  });
});
