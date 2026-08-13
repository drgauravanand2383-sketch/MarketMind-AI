import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { ScreeningResultsPage } from "@/features/screening/screening-results-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildScreeningProfile, buildScreenResult } from "@/test/msw/fixtures";
import { screeningResultStore } from "@/test/msw/handlers";
import { resetScreeningStore } from "@/test/msw/screening-store";
import { useComparisonStore } from "@/store/comparison-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("ScreeningResultsPage", () => {
  beforeEach(() => {
    resetScreeningStore([buildScreeningProfile({ id: "p1", name: "Large Cap" })]);
    screeningResultStore.reset();
    useComparisonStore.setState({ researchRequestIds: [], screeningResultIds: [] });
  });

  it("renders matched and unmatched companies with the profile's own name as the heading", async () => {
    const resultId = screeningResultStore.put([
      "p1",
      [
        buildScreenResult({ ticker: "AAPL", company_name: "Apple Inc.", passed: true, score: 100 }),
        buildScreenResult({ ticker: "TINY", company_name: "Tiny Co", passed: false, score: 0, matched_filters: [], failed_filters: [{ filter_id: "f1", field: "market_cap", operator: "GREATER_THAN", passed: false, reason: "Too small." }] }),
      ],
    ] as const);

    renderWithQueryClient(<ScreeningResultsPage resultId={resultId} />);

    expect(await screen.findByRole("heading", { name: "Large Cap" }, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText("1 of 2 companies matched")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("TINY")).toBeInTheDocument();
  });

  it("filters to only matched companies via the match-status toggle", async () => {
    const user = userEvent.setup();
    const resultId = screeningResultStore.put([
      "p1",
      [buildScreenResult({ ticker: "AAPL", passed: true }), buildScreenResult({ ticker: "TINY", passed: false })],
    ] as const);
    renderWithQueryClient(<ScreeningResultsPage resultId={resultId} />);
    await screen.findByText("AAPL");

    await user.click(screen.getByRole("button", { name: "Matched" }));

    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("TINY")).not.toBeInTheDocument();
  });

  it("searches results by ticker", async () => {
    const user = userEvent.setup();
    const resultId = screeningResultStore.put([
      "p1",
      [buildScreenResult({ ticker: "AAPL" }), buildScreenResult({ ticker: "MSFT", company_name: "Microsoft" })],
    ] as const);
    renderWithQueryClient(<ScreeningResultsPage resultId={resultId} />);
    await screen.findByText("AAPL");

    await user.type(screen.getByLabelText("Search results by ticker or company name"), "MSFT");

    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });

  it("toggles the comparison-selection store when 'Add to comparison' is clicked", async () => {
    const user = userEvent.setup();
    const resultId = screeningResultStore.put(["p1", [buildScreenResult()]] as const);
    renderWithQueryClient(<ScreeningResultsPage resultId={resultId} />);
    await screen.findByText("AAPL");

    await user.click(screen.getByRole("button", { name: "Add to comparison" }));

    expect(useComparisonStore.getState().screeningResultIds).toEqual([resultId]);
  });

  it("shows a 'no longer available' state for a result_id the backend doesn't have cached", async () => {
    renderWithQueryClient(<ScreeningResultsPage resultId="stale-id" />);
    await waitFor(() => {
      expect(screen.getByText("Result no longer available")).toBeInTheDocument();
    });
  });
});
