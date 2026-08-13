import { beforeEach, describe, expect, it } from "vitest";
import { useDecisionWorkspaceStore } from "@/store/decision-workspace-store";

describe("decision-workspace-store", () => {
  beforeEach(() => {
    useDecisionWorkspaceStore.setState({
      selectedPortfolioId: "",
      activeTab: "overview",
      activeRecommendationResultId: null,
      chartPreferences: { showDataLabels: false },
    });
  });

  it("setSelectedPortfolioId resets the active recommendation result", () => {
    useDecisionWorkspaceStore.getState().setActiveRecommendationResultId("rec-1");
    useDecisionWorkspaceStore.getState().setSelectedPortfolioId("wl-2");

    expect(useDecisionWorkspaceStore.getState().selectedPortfolioId).toBe("wl-2");
    expect(useDecisionWorkspaceStore.getState().activeRecommendationResultId).toBeNull();
  });

  it("setActiveTab switches the active tab", () => {
    useDecisionWorkspaceStore.getState().setActiveTab("strategy");
    expect(useDecisionWorkspaceStore.getState().activeTab).toBe("strategy");
  });

  it("toggleShowDataLabels flips the chart preference", () => {
    useDecisionWorkspaceStore.getState().toggleShowDataLabels();
    expect(useDecisionWorkspaceStore.getState().chartPreferences.showDataLabels).toBe(true);

    useDecisionWorkspaceStore.getState().toggleShowDataLabels();
    expect(useDecisionWorkspaceStore.getState().chartPreferences.showDataLabels).toBe(false);
  });
});
