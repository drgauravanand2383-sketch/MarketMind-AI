import { describe, expect, it } from "vitest";
import { toNotificationEntry } from "@/lib/realtime-notifications";
import { buildDomainEvent } from "@/test/mock-websocket";
import {
  buildAlert,
  buildBacktestResult,
  buildBacktestRun,
  buildExplainabilityResult,
  buildRecommendationResult,
  buildRiskAssessment,
  buildStrategyEvaluationResult,
  testApplicationHealth,
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
});
