import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResearchResultPage } from "@/features/research/research-result-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildResearchReport } from "@/test/msw/fixtures";
import { researchReportStore } from "@/test/msw/handlers";
import { useComparisonStore } from "@/store/comparison-store";

describe("ResearchResultPage", () => {
  beforeEach(() => {
    researchReportStore.reset();
    useComparisonStore.setState({ researchRequestIds: [], screeningResultIds: [] });
  });

  it("renders the report's overview, summary metrics, and exposure sections", async () => {
    const requestId = researchReportStore.put(buildResearchReport());
    renderWithQueryClient(<ResearchResultPage requestId={requestId} />);

    expect(await screen.findByRole("heading", { name: /Apple Inc\./ })).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument(); // overall_confidence
    expect(screen.getByText("Matched")).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument(); // sector exposure
    expect(screen.getByText(/Apple shows strong evidence coverage/)).toBeInTheDocument();
  });

  it("shows a no-narrative empty state when narrative is null (unmatched company)", async () => {
    const requestId = researchReportStore.put(
      buildResearchReport({
        narrative: null,
        company_overview: { company_name: "Unknown Co", ticker: null, matched: false, entity_recognized: false, mention_count: 0, supporting_record_ids: [] },
      }),
    );
    renderWithQueryClient(<ResearchResultPage requestId={requestId} />);

    expect(await screen.findByText("No narrative available")).toBeInTheDocument();
    expect(screen.getByText("Unmatched")).toBeInTheDocument();
  });

  it("toggles the comparison-selection store when 'Add to comparison' is clicked", async () => {
    const user = userEvent.setup();
    const requestId = researchReportStore.put(buildResearchReport());
    renderWithQueryClient(<ResearchResultPage requestId={requestId} />);

    const button = await screen.findByRole("button", { name: "Add to comparison" });
    await user.click(button);

    expect(useComparisonStore.getState().researchRequestIds).toEqual([requestId]);
    expect(await screen.findByRole("button", { name: "Selected for comparison" })).toBeInTheDocument();
  });

  it("shows a 'no longer available' state for a request_id the backend doesn't have cached", async () => {
    renderWithQueryClient(<ResearchResultPage requestId="stale-id" />);

    await waitFor(() => {
      expect(screen.getByText("Report no longer available")).toBeInTheDocument();
    });
  });
});
