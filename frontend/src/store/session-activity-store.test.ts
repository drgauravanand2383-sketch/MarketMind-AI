import { beforeEach, describe, expect, it } from "vitest";
import { useSessionActivityStore } from "@/store/session-activity-store";

describe("session-activity-store", () => {
  beforeEach(() => {
    useSessionActivityStore.setState({ recentResearch: [], recentScreeningRuns: [] });
  });

  it("adds a research entry to the front of the list", () => {
    useSessionActivityStore.getState().addResearch({ requestId: "r1", companyName: "Apple", ticker: "AAPL", matched: true, ranAt: "2026-01-01T00:00:00Z" });
    useSessionActivityStore.getState().addResearch({ requestId: "r2", companyName: "Microsoft", ticker: "MSFT", matched: true, ranAt: "2026-01-02T00:00:00Z" });

    const recent = useSessionActivityStore.getState().recentResearch;
    expect(recent).toHaveLength(2);
    expect(recent[0]?.requestId).toBe("r2");
  });

  it("caps the research list at 10 entries", () => {
    for (let i = 0; i < 12; i += 1) {
      useSessionActivityStore.getState().addResearch({ requestId: `r${String(i)}`, companyName: "X", ticker: null, matched: true, ranAt: "2026-01-01T00:00:00Z" });
    }
    expect(useSessionActivityStore.getState().recentResearch).toHaveLength(10);
  });

  it("adds a screening run entry to the front of the list", () => {
    useSessionActivityStore.getState().addScreeningRun({ resultId: "res1", profileId: "p1", profileName: "Large Cap", companyCount: 2, matchedCount: 1, ranAt: "2026-01-01T00:00:00Z" });
    expect(useSessionActivityStore.getState().recentScreeningRuns).toHaveLength(1);
    expect(useSessionActivityStore.getState().recentScreeningRuns[0]?.profileName).toBe("Large Cap");
  });

  it("clear() empties both lists", () => {
    useSessionActivityStore.getState().addResearch({ requestId: "r1", companyName: "Apple", ticker: "AAPL", matched: true, ranAt: "2026-01-01T00:00:00Z" });
    useSessionActivityStore.getState().addScreeningRun({ resultId: "res1", profileId: "p1", profileName: "Large Cap", companyCount: 1, matchedCount: 1, ranAt: "2026-01-01T00:00:00Z" });

    useSessionActivityStore.getState().clear();

    expect(useSessionActivityStore.getState().recentResearch).toHaveLength(0);
    expect(useSessionActivityStore.getState().recentScreeningRuns).toHaveLength(0);
  });
});
