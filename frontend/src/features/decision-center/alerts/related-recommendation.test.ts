import { describe, expect, it } from "vitest";
import { findRelatedRecommendation } from "@/features/decision-center/alerts/related-recommendation";
import { buildRecommendationCandidate } from "@/test/msw/fixtures";

describe("findRelatedRecommendation", () => {
  it("matches a candidate sharing the alert's ticker", () => {
    const candidates = [buildRecommendationCandidate({ ticker: "AAPL" }), buildRecommendationCandidate({ ticker: "MSFT" })];
    expect(findRelatedRecommendation("MSFT", candidates)?.ticker).toBe("MSFT");
  });

  it("returns null when no candidate shares the ticker", () => {
    const candidates = [buildRecommendationCandidate({ ticker: "AAPL" })];
    expect(findRelatedRecommendation("TSLA", candidates)).toBeNull();
  });

  it("returns null when no candidates are loaded at all", () => {
    expect(findRelatedRecommendation("AAPL", undefined)).toBeNull();
  });
});
