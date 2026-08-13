import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { GenerateExplanationForm } from "@/features/historical-analysis/explainability/generate-explanation-form";
import { renderWithQueryClient } from "@/test/test-utils";
import { resetExplainabilityStore } from "@/test/msw/explainability-store";
import { useDecisionHistoryStore } from "@/store/decision-history-store";

const navigateSpy = vi.fn();
vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, useNavigate: () => navigateSpy, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("GenerateExplanationForm", () => {
  beforeEach(() => {
    navigateSpy.mockClear();
    resetExplainabilityStore();
    useDecisionHistoryStore.setState({ entries: [] });
  });

  it("shows an empty state instead of the form when no recommendation results exist this session", () => {
    renderWithQueryClient(<GenerateExplanationForm />);
    expect(screen.getByText("No recommendation results this session yet")).toBeInTheDocument();
  });

  it("requires selecting a recommendation result before submitting", async () => {
    useDecisionHistoryStore.setState({
      entries: [{ kind: "recommendations_generated", id: "h1", portfolioId: "wl-1", requestId: "rec-1", candidateCount: 3, occurredAt: "2026-01-15T00:00:00Z" }],
    });
    const user = userEvent.setup();
    renderWithQueryClient(<GenerateExplanationForm />);

    await user.type(screen.getByLabelText("Name"), "Why AAPL");
    await user.click(screen.getByRole("button", { name: /generate explanation/i }));

    expect(await screen.findByText("Select a recommendation result")).toBeInTheDocument();
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it("generates an explanation and navigates to its detail page", async () => {
    useDecisionHistoryStore.setState({
      entries: [{ kind: "recommendations_generated", id: "h1", portfolioId: "wl-1", requestId: "rec-1", candidateCount: 3, occurredAt: "2026-01-15T00:00:00Z" }],
    });
    const user = userEvent.setup();
    renderWithQueryClient(<GenerateExplanationForm />);

    await user.type(screen.getByLabelText("Name"), "Why AAPL");
    await user.selectOptions(screen.getByLabelText("Recommendation result"), "rec-1");
    await user.click(screen.getByRole("button", { name: /generate explanation/i }));

    await waitFor(() => {
      expect(navigateSpy).toHaveBeenCalled();
    });
    const [navigateArgs] = navigateSpy.mock.calls[0] as [{ to: string; params: { requestId: string } }];
    expect(navigateArgs.to).toBe("/historical-analysis/explainability/$requestId");
    expect(navigateArgs.params.requestId).toBeTruthy();

    expect(useDecisionHistoryStore.getState().entries[0]).toMatchObject({ kind: "explainability_generated", recommendationResultId: "rec-1" });
  });
});
