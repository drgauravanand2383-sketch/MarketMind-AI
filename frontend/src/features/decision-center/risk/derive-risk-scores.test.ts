import { describe, expect, it } from "vitest";
import { deriveRiskScores, findRiskMetricByCategory } from "@/features/decision-center/risk/derive-risk-scores";
import type { RiskMetric } from "@/types/portfolio";

function metric(overrides: Partial<RiskMetric> = {}): RiskMetric {
  return { metric_name: "Test metric", category: "SECTOR", value: 0.5, score: 50, severity: "MODERATE", description: "Test.", ...overrides };
}

describe("findRiskMetricByCategory", () => {
  it("finds a metric by category", () => {
    const metrics = [metric({ category: "DIVERSIFICATION", score: 70 })];
    expect(findRiskMetricByCategory(metrics, "DIVERSIFICATION")?.score).toBe(70);
  });

  it("returns null when no metric of that category exists — never fabricates one", () => {
    expect(findRiskMetricByCategory([], "VOLATILITY")).toBeNull();
  });
});

describe("deriveRiskScores", () => {
  it("derives all four named scores from categorized risk_metrics", () => {
    const metrics = [
      metric({ category: "DIVERSIFICATION", score: 60 }),
      metric({ category: "CONCENTRATION", score: 40 }),
      metric({ category: "LIQUIDITY", score: 80 }),
      metric({ category: "VOLATILITY", score: 30 }),
    ];
    const derived = deriveRiskScores(metrics);
    expect(derived.diversification?.score).toBe(60);
    expect(derived.concentration?.score).toBe(40);
    expect(derived.liquidity?.score).toBe(80);
    expect(derived.volatility?.score).toBe(30);
  });

  it("leaves a category null when the engine didn't emit it for this portfolio", () => {
    const derived = deriveRiskScores([metric({ category: "SECTOR" })]);
    expect(derived.diversification).toBeNull();
    expect(derived.concentration).toBeNull();
    expect(derived.liquidity).toBeNull();
    expect(derived.volatility).toBeNull();
  });
});
