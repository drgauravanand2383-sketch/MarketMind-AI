import { beforeEach, describe, expect, it } from "vitest";
import { useComparisonStore } from "@/store/comparison-store";

describe("comparison-store", () => {
  beforeEach(() => {
    useComparisonStore.setState({ researchRequestIds: [], screeningResultIds: [] });
  });

  it("toggleResearch selects and deselects a report", () => {
    useComparisonStore.getState().toggleResearch("r1");
    expect(useComparisonStore.getState().researchRequestIds).toEqual(["r1"]);

    useComparisonStore.getState().toggleResearch("r1");
    expect(useComparisonStore.getState().researchRequestIds).toEqual([]);
  });

  it("caps research selection at 2, dropping the oldest", () => {
    useComparisonStore.getState().toggleResearch("r1");
    useComparisonStore.getState().toggleResearch("r2");
    useComparisonStore.getState().toggleResearch("r3");

    expect(useComparisonStore.getState().researchRequestIds).toEqual(["r2", "r3"]);
  });

  it("caps screening result selection at 4, dropping the oldest", () => {
    for (const id of ["s1", "s2", "s3", "s4", "s5"]) {
      useComparisonStore.getState().toggleScreeningResult(id);
    }
    expect(useComparisonStore.getState().screeningResultIds).toEqual(["s2", "s3", "s4", "s5"]);
  });

  it("clearResearch/clearScreeningResults empty their own list only", () => {
    useComparisonStore.getState().toggleResearch("r1");
    useComparisonStore.getState().toggleScreeningResult("s1");

    useComparisonStore.getState().clearResearch();

    expect(useComparisonStore.getState().researchRequestIds).toEqual([]);
    expect(useComparisonStore.getState().screeningResultIds).toEqual(["s1"]);
  });
});
