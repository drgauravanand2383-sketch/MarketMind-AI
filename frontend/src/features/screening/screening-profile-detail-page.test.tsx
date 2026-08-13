import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { ScreeningProfileDetailPage } from "@/features/screening/screening-profile-detail-page";
import { NotificationCenter } from "@/components/notifications/notification-center";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildScreeningProfile } from "@/test/msw/fixtures";
import { resetScreeningStore } from "@/test/msw/screening-store";
import { screeningResultStore } from "@/test/msw/handlers";
import { useNotificationStore } from "@/store/notification-store";

const navigateSpy = vi.fn();
vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, useNavigate: () => navigateSpy };
});

describe("ScreeningProfileDetailPage", () => {
  beforeEach(() => {
    navigateSpy.mockClear();
    useNotificationStore.setState({ notifications: [] });
    resetScreeningStore([buildScreeningProfile({ id: "p1", name: "Large Cap" })]);
    screeningResultStore.reset();
  });

  it("renders the profile's existing filter in the builder", async () => {
    renderWithQueryClient(<ScreeningProfileDetailPage profileId="p1" />);
    expect(await screen.findByLabelText("Field")).toHaveValue("market_cap");
    expect(screen.getByLabelText("Operator")).toHaveValue("GREATER_THAN");
  });

  it("adds a filter, edits it, and saves — showing a success notification", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(
      <>
        <ScreeningProfileDetailPage profileId="p1" />
        <NotificationCenter />
      </>,
    );
    await screen.findByLabelText("Field");

    await user.click(screen.getByRole("button", { name: "Add filter" }));
    expect(screen.getAllByLabelText("Field")).toHaveLength(2);

    // The newly added filter defaults to no value, which the builder's
    // own validation correctly flags — give it one so Save is enabled.
    const valueInputs = screen.getAllByLabelText("Value");
    const newFilterValueInput = valueInputs[1];
    expect(newFilterValueInput).toBeDefined();
    if (newFilterValueInput) {
      await user.type(newFilterValueInput, "5000000");
    }

    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(/updated/i);
    });
  });

  it("disables Save when a BETWEEN filter's low bound exceeds its high bound", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ScreeningProfileDetailPage profileId="p1" />);
    await screen.findByLabelText("Operator");

    await user.selectOptions(screen.getByLabelText("Operator"), "BETWEEN");
    await user.type(screen.getByLabelText("Low bound"), "100");
    await user.type(screen.getByLabelText("High bound"), "10");

    expect(await screen.findByRole("alert")).toHaveTextContent(/low value can't exceed/i);
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("runs the screen against entered companies and navigates to the results page", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ScreeningProfileDetailPage profileId="p1" />);
    await screen.findByLabelText("Ticker");

    await user.type(screen.getByLabelText("Ticker"), "AAPL");
    await user.type(screen.getByLabelText("Company name"), "Apple Inc.");
    await user.type(screen.getByLabelText("Market cap"), "2000000");

    await user.click(screen.getByRole("button", { name: "Run screening" }));

    await waitFor(() => {
      expect(navigateSpy).toHaveBeenCalled();
    });
    const [navigateArgs] = navigateSpy.mock.calls[0] as [{ to: string; params: { resultId: string } }];
    expect(navigateArgs.to).toBe("/screening/results/$resultId");
    expect(navigateArgs.params.resultId).toBeTruthy();
  });
});
