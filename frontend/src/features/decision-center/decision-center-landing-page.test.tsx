import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type * as ReactRouterModule from "@tanstack/react-router";
import { DecisionCenterLandingPage } from "@/features/decision-center/decision-center-landing-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { resetWatchlistStore } from "@/test/msw/watchlist-store";
import { buildWatchlist } from "@/test/msw/fixtures";
import { useDecisionHistoryStore } from "@/store/decision-history-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return {
    ...actual,
    Link: (props: { to: string; params?: Record<string, string>; children?: ReactNode }) => {
      const href = Object.entries(props.params ?? {}).reduce((path, [key, value]) => path.replace(`$${key}`, value), props.to);
      return <a href={href}>{props.children}</a>;
    },
  };
});

describe("DecisionCenterLandingPage", () => {
  beforeEach(() => {
    resetWatchlistStore([buildWatchlist({ id: "wl-1", name: "Tech Growth" })]);
    useDecisionHistoryStore.setState({ entries: [] });
  });

  it("lists the user's watchlists as portfolio choices", async () => {
    renderWithQueryClient(<DecisionCenterLandingPage />);
    await waitFor(() => {
      expect(screen.getByText("Tech Growth")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Open workspace" })).toHaveAttribute("href", "/decisions/wl-1");
  });

  it("shows an empty decision history before any session activity", async () => {
    renderWithQueryClient(<DecisionCenterLandingPage />);
    await waitFor(() => {
      expect(screen.getByText("Tech Growth")).toBeInTheDocument();
    });
    expect(screen.getByText("No decisions made yet this session")).toBeInTheDocument();
  });

  it("lists a session decision-history entry with a link back into its portfolio's workspace", async () => {
    useDecisionHistoryStore.getState().addEntry({
      kind: "recommendations_generated",
      id: "e1",
      portfolioId: "wl-1",
      requestId: "rec-1",
      candidateCount: 3,
      occurredAt: "2026-01-01T00:00:00Z",
    });

    renderWithQueryClient(<DecisionCenterLandingPage />);

    expect(await screen.findByText(/Generated 3 recommendations/)).toBeInTheDocument();
  });
});
