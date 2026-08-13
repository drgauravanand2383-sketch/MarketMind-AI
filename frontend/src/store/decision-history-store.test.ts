import { beforeEach, describe, expect, it } from "vitest";
import { useDecisionHistoryStore } from "@/store/decision-history-store";

describe("decision-history-store", () => {
  beforeEach(() => {
    useDecisionHistoryStore.setState({ entries: [] });
  });

  it("adds an entry to the front of the list", () => {
    useDecisionHistoryStore.getState().addEntry({ kind: "risk_loaded", id: "r1", portfolioId: "wl-1", requestId: "risk-1", occurredAt: "2026-01-01T00:00:00Z" });
    useDecisionHistoryStore.getState().addEntry({ kind: "alerts_evaluated", id: "r2", generatedCount: 2, suppressedCount: 0, occurredAt: "2026-01-02T00:00:00Z" });

    const entries = useDecisionHistoryStore.getState().entries;
    expect(entries).toHaveLength(2);
    expect(entries[0]?.id).toBe("r2");
  });

  it("caps the list at 20 entries", () => {
    for (let i = 0; i < 25; i += 1) {
      useDecisionHistoryStore.getState().addEntry({ kind: "signals_evaluated", id: `e${String(i)}`, resultId: `res-${String(i)}`, definitionId: "def-1", triggeredCount: 1, occurredAt: "2026-01-01T00:00:00Z" });
    }
    expect(useDecisionHistoryStore.getState().entries).toHaveLength(20);
  });

  it("clear() empties the list", () => {
    useDecisionHistoryStore.getState().addEntry({ kind: "risk_loaded", id: "r1", portfolioId: "wl-1", requestId: "risk-1", occurredAt: "2026-01-01T00:00:00Z" });
    useDecisionHistoryStore.getState().clear();
    expect(useDecisionHistoryStore.getState().entries).toHaveLength(0);
  });
});
