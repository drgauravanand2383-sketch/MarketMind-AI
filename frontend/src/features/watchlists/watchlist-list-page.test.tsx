import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { WatchlistListPage } from "@/features/watchlists/watchlist-list-page";
import { NotificationCenter } from "@/components/notifications/notification-center";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildWatchlist } from "@/test/msw/fixtures";
import { resetWatchlistStore } from "@/test/msw/watchlist-store";
import { useWatchlistUiStore } from "@/store/watchlist-ui-store";
import { useNotificationStore } from "@/store/notification-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({ to, children }: { to: string; children?: ReactNode }) => <a href={to}>{children}</a>,
  };
});

function resetUiStore(): void {
  useWatchlistUiStore.setState({
    filters: { name: "", sector: "", country: "", theme: "", ticker: "" },
    sort: "updated_at",
    direction: "desc",
    page: 1,
    pageSize: 20,
    filtersExpanded: false,
  });
}

/** The adaptive layout renders a desktop `<table>` AND a mobile
 * `<ul>` card list simultaneously (CSS, not React, decides which shows)
 * — so every watchlist name legitimately appears twice in the DOM.
 * This always resolves the desktop table's copy (rendered first). */
function getDesktopRow(name: string): HTMLElement {
  const row = screen.getAllByText(name)[0]?.closest("tr");
  if (!row) throw new Error(`No table row found for "${name}"`);
  return row;
}

describe("WatchlistListPage", () => {
  beforeEach(() => {
    resetUiStore();
    useNotificationStore.setState({ notifications: [] });
    resetWatchlistStore([
      buildWatchlist({ id: "wl-1", name: "Tech Growth", updated_at: "2026-01-05T00:00:00Z" }),
      buildWatchlist({ id: "wl-2", name: "Healthcare Value", updated_at: "2026-01-06T00:00:00Z", items: [] }),
    ]);
  });

  it("renders the seeded watchlists once loading finishes", async () => {
    renderWithQueryClient(<WatchlistListPage />);

    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("Tech Growth").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("Healthcare Value").length).toBeGreaterThan(0);
  });

  it("shows an empty state when there are no watchlists", async () => {
    resetWatchlistStore([]);
    renderWithQueryClient(<WatchlistListPage />);

    expect(await screen.findByText("No watchlists found")).toBeInTheDocument();
  });

  it("creates a watchlist through the dialog and shows a success notification", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(
      <>
        <WatchlistListPage />
        <NotificationCenter />
      </>,
    );
    await waitFor(() => {
      expect(screen.getAllByText("Tech Growth").length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole("button", { name: "Create watchlist" }));
    const dialog = screen.getByRole("dialog", { name: "Create watchlist" });
    await user.type(within(dialog).getByLabelText("Name"), "New Watchlist");
    await user.click(within(dialog).getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(screen.getAllByText("New Watchlist").length).toBeGreaterThan(0);
    });
    expect(screen.getByRole("status")).toHaveTextContent(/created/i);
  });

  it("filters watchlists by name through the search box", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WatchlistListPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Tech Growth").length).toBeGreaterThan(0);
    });

    await user.type(screen.getByLabelText("Search watchlists by name"), "health");

    await waitFor(
      () => {
        expect(screen.queryByText("Tech Growth")).not.toBeInTheDocument();
      },
      { timeout: 2000 },
    );
    expect(screen.getAllByText("Healthcare Value").length).toBeGreaterThan(0);
  });

  it("renames a watchlist via the row action and rename dialog", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WatchlistListPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Tech Growth").length).toBeGreaterThan(0);
    });

    const row = getDesktopRow("Tech Growth");
    await user.click(within(row).getByRole("button", { name: "Rename" }));

    const dialog = screen.getByRole("dialog", { name: "Rename watchlist" });
    const nameInput = within(dialog).getByLabelText("Name");
    await user.clear(nameInput);
    await user.type(nameInput, "Tech Growth Renamed");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(screen.getAllByText("Tech Growth Renamed").length).toBeGreaterThan(0);
    });
  });

  it("deletes a watchlist after confirming in the dialog", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WatchlistListPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Tech Growth").length).toBeGreaterThan(0);
    });

    const row = getDesktopRow("Tech Growth");
    await user.click(within(row).getByRole("button", { name: "Delete" }));

    const dialog = screen.getByRole("dialog", { name: "Delete watchlist" });
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(screen.queryByText("Tech Growth")).not.toBeInTheDocument();
    });
  });

  it("toggles sort direction when a sortable column header is clicked", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WatchlistListPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Tech Growth").length).toBeGreaterThan(0);
    });

    const nameHeader = screen.getByRole("columnheader", { name: /Name/ });
    expect(nameHeader).toHaveAttribute("aria-sort", "none");

    await user.click(within(nameHeader).getByRole("button"));

    await waitFor(() => {
      expect(nameHeader).toHaveAttribute("aria-sort", "ascending");
    });
    expect(useWatchlistUiStore.getState().sort).toBe("name");
  });

  it("renders both a table (desktop) and a card list (mobile) for the same data — adaptive layout", async () => {
    renderWithQueryClient(<WatchlistListPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Tech Growth").length).toBeGreaterThan(0);
    });

    expect(document.querySelector("table.sm\\:table")).toBeInTheDocument();
    expect(document.querySelector("ul.sm\\:hidden")).toBeInTheDocument();
  });
});
