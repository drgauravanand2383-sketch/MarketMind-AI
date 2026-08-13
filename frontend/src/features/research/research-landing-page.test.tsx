import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { ResearchLandingPage } from "@/features/research/research-landing-page";
import { NotificationCenter } from "@/components/notifications/notification-center";
import { renderWithQueryClient } from "@/test/test-utils";
import { researchReportStore } from "@/test/msw/handlers";
import { useNotificationStore } from "@/store/notification-store";
import { useSessionActivityStore } from "@/store/session-activity-store";

const navigateSpy = vi.fn();
vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return {
    ...actual,
    useNavigate: () => navigateSpy,
    Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a>,
  };
});

describe("ResearchLandingPage", () => {
  beforeEach(() => {
    navigateSpy.mockClear();
    researchReportStore.reset();
    useNotificationStore.setState({ notifications: [] });
    useSessionActivityStore.setState({ recentResearch: [], recentScreeningRuns: [] });
  });

  it("shows an empty session-recent list before any research has run", () => {
    renderWithQueryClient(<ResearchLandingPage />);
    expect(screen.getByText("No research run yet this session")).toBeInTheDocument();
  });

  it("runs research, shows started/completed notifications, and navigates to the result page", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(
      <>
        <ResearchLandingPage />
        <NotificationCenter />
      </>,
    );

    await user.type(screen.getByLabelText("Company name"), "Apple Inc.");
    await user.type(screen.getByLabelText("Ticker (optional)"), "AAPL");
    await user.click(screen.getByRole("button", { name: /run research/i }));

    expect(await screen.findByText(/Researching Apple Inc\./i)).toBeInTheDocument();

    await waitFor(() => {
      expect(navigateSpy).toHaveBeenCalled();
    });
    const [navigateArgs] = navigateSpy.mock.calls[0] as [{ to: string; params: { requestId: string } }];
    expect(navigateArgs.to).toBe("/research/$requestId");
    expect(navigateArgs.params.requestId).toBeTruthy();
    expect(screen.getByText(/Research complete for Apple Inc\./i)).toBeInTheDocument();
  });

  it("requires a company name before submitting", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ResearchLandingPage />);

    await user.click(screen.getByRole("button", { name: /run research/i }));

    expect(await screen.findByText("Company name is required")).toBeInTheDocument();
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it("lists a completed run in the session-recent list", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ResearchLandingPage />);

    await user.type(screen.getByLabelText("Company name"), "Microsoft");
    await user.click(screen.getByRole("button", { name: /run research/i }));

    await waitFor(() => {
      expect(useSessionActivityStore.getState().recentResearch).toHaveLength(1);
    });
    expect(screen.getAllByText("Microsoft").length).toBeGreaterThan(0);
  });
});
