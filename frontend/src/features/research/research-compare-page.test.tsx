import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { ResearchComparePage } from "@/features/research/research-compare-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildResearchReport } from "@/test/msw/fixtures";
import { researchReportStore } from "@/test/msw/handlers";
import { useComparisonStore } from "@/store/comparison-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("ResearchComparePage", () => {
  beforeEach(() => {
    researchReportStore.reset();
    useComparisonStore.setState({ researchRequestIds: [], screeningResultIds: [] });
  });

  it("shows an empty state when fewer than 2 reports are selected", () => {
    renderWithQueryClient(<ResearchComparePage />);
    expect(screen.getByText("Select two reports to compare")).toBeInTheDocument();
  });

  it("renders both selected reports side by side and flags a differing field", async () => {
    const idA = researchReportStore.put(
      buildResearchReport({ company_overview: { company_name: "Apple Inc.", ticker: "AAPL", matched: true, entity_recognized: true, mention_count: 12, supporting_record_ids: [] } }),
    );
    const idB = researchReportStore.put(
      buildResearchReport({ company_overview: { company_name: "Microsoft", ticker: "MSFT", matched: true, entity_recognized: true, mention_count: 5, supporting_record_ids: [] } }),
    );
    useComparisonStore.setState({ researchRequestIds: [idA, idB], screeningResultIds: [] });

    renderWithQueryClient(<ResearchComparePage />);

    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: "Apple Inc." })).toBeInTheDocument();
    });
    expect(screen.getByRole("columnheader", { name: "Microsoft" })).toBeInTheDocument();

    const mentionsRow = screen.getByText("Mentions").closest("tr");
    expect(mentionsRow).not.toBeNull();
    expect(mentionsRow).toHaveClass("bg-amber-50");
  });

  it("clears the comparison selection", async () => {
    const idA = researchReportStore.put(buildResearchReport());
    const idB = researchReportStore.put(buildResearchReport());
    useComparisonStore.setState({ researchRequestIds: [idA, idB], screeningResultIds: [] });

    renderWithQueryClient(<ResearchComparePage />);
    await waitFor(() => {
      expect(screen.getAllByRole("row").length).toBeGreaterThan(1);
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Clear selection" }));

    expect(useComparisonStore.getState().researchRequestIds).toEqual([]);
  });
});
