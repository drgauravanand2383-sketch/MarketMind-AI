import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { ScreeningLandingPage } from "@/features/screening/screening-landing-page";
import { NotificationCenter } from "@/components/notifications/notification-center";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildScreeningProfile } from "@/test/msw/fixtures";
import { resetScreeningStore } from "@/test/msw/screening-store";
import { useNotificationStore } from "@/store/notification-store";
import { useScreeningUiStore } from "@/store/screening-ui-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

function resetUiStore(): void {
  useScreeningUiStore.setState({ nameSearch: "", sort: "updated_at", direction: "desc", page: 1, pageSize: 20 });
}

function getDesktopRow(name: string): HTMLElement {
  const row = screen.getAllByText(name)[0]?.closest("tr");
  if (!row) throw new Error(`No table row found for "${name}"`);
  return row;
}

describe("ScreeningLandingPage", () => {
  beforeEach(() => {
    resetUiStore();
    useNotificationStore.setState({ notifications: [] });
    resetScreeningStore([
      buildScreeningProfile({ id: "p1", name: "Large Cap", updated_at: "2026-01-05T00:00:00Z" }),
      buildScreeningProfile({ id: "p2", name: "Small Cap Value", updated_at: "2026-01-06T00:00:00Z" }),
    ]);
  });

  it("renders the seeded profiles once loading finishes", async () => {
    renderWithQueryClient(<ScreeningLandingPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Large Cap").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("Small Cap Value").length).toBeGreaterThan(0);
  });

  it("shows an empty state when there are no screens", async () => {
    resetScreeningStore([]);
    renderWithQueryClient(<ScreeningLandingPage />);
    expect(await screen.findByText("No screens found")).toBeInTheDocument();
  });

  it("creates a screen through the dialog and shows a success notification", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(
      <>
        <ScreeningLandingPage />
        <NotificationCenter />
      </>,
    );
    await waitFor(() => {
      expect(screen.getAllByText("Large Cap").length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole("button", { name: "Create screen" }));
    const dialog = screen.getByRole("dialog", { name: "Create screen" });
    await user.type(within(dialog).getByLabelText("Name"), "Momentum Screen");
    await user.click(within(dialog).getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(screen.getAllByText("Momentum Screen").length).toBeGreaterThan(0);
    });
    expect(screen.getByRole("status")).toHaveTextContent(/created/i);
  });

  it("filters screens by name through the search box", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ScreeningLandingPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Large Cap").length).toBeGreaterThan(0);
    });

    await user.type(screen.getByLabelText("Search screening profiles by name"), "small");

    await waitFor(
      () => {
        expect(screen.queryByText("Large Cap")).not.toBeInTheDocument();
      },
      { timeout: 2000 },
    );
    expect(screen.getAllByText("Small Cap Value").length).toBeGreaterThan(0);
  });

  it("renames a screen via the row action and rename dialog", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ScreeningLandingPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Large Cap").length).toBeGreaterThan(0);
    });

    const row = getDesktopRow("Large Cap");
    await user.click(within(row).getByRole("button", { name: "Rename" }));

    const dialog = screen.getByRole("dialog", { name: "Rename screen" });
    const nameInput = within(dialog).getByLabelText("Name");
    await user.clear(nameInput);
    await user.type(nameInput, "Large Cap Renamed");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(screen.getAllByText("Large Cap Renamed").length).toBeGreaterThan(0);
    });
  });

  it("duplicates a screen via the row action and duplicate dialog", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ScreeningLandingPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Large Cap").length).toBeGreaterThan(0);
    });

    const row = getDesktopRow("Large Cap");
    await user.click(within(row).getByRole("button", { name: "Duplicate" }));

    const dialog = screen.getByRole("dialog", { name: "Duplicate screen" });
    expect(within(dialog).getByLabelText("New name")).toHaveValue("Large Cap (copy)");
    await user.click(within(dialog).getByRole("button", { name: "Duplicate" }));

    await waitFor(() => {
      expect(screen.getAllByText("Large Cap (copy)").length).toBeGreaterThan(0);
    });
  });

  it("deletes a screen after confirming in the dialog", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ScreeningLandingPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Large Cap").length).toBeGreaterThan(0);
    });

    const row = getDesktopRow("Large Cap");
    await user.click(within(row).getByRole("button", { name: "Delete" }));

    const dialog = screen.getByRole("dialog", { name: "Delete screen" });
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(screen.queryByText("Large Cap")).not.toBeInTheDocument();
    });
  });

  it("toggles sort direction when a sortable column header is clicked", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ScreeningLandingPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Large Cap").length).toBeGreaterThan(0);
    });

    const nameHeader = screen.getByRole("columnheader", { name: /Name/ });
    await user.click(within(nameHeader).getByRole("button"));

    await waitFor(() => {
      expect(nameHeader).toHaveAttribute("aria-sort", "ascending");
    });
    expect(useScreeningUiStore.getState().sort).toBe("name");
  });

  it("shows the session-only recent screening runs empty state before any run", () => {
    renderWithQueryClient(<ScreeningLandingPage />);
    expect(screen.getByText("No screens run yet this session")).toBeInTheDocument();
  });
});
