import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { WatchlistDetailPage } from "@/features/watchlists/watchlist-detail-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildMeta, buildWatchlist, buildWatchlistItem } from "@/test/msw/fixtures";
import { resetWatchlistStore } from "@/test/msw/watchlist-store";
import { API_BASE_URL } from "@/services/api/config";

vi.stubGlobal("scrollTo", () => undefined);

/** `CompanyTable` renders exactly one of a desktop `<table>` or a mobile
 * `<ul>` card list, chosen via `useMediaQuery` (Milestone 9 fix — it used
 * to render both simultaneously with one hidden via CSS). jsdom has no
 * `window.matchMedia`, so the hook's own fallback always resolves to
 * `true` (desktop) here — the table is what's actually in the DOM. */
function getTable(): HTMLElement {
  return screen.getByRole("table", { name: "Companies in this watchlist" });
}

describe("WatchlistDetailPage", () => {
  beforeEach(() => {
    resetWatchlistStore([
      buildWatchlist({
        id: "wl-1",
        name: "Tech Growth",
        items: [buildWatchlistItem({ ticker: "AAPL", sector: "Technology", country: "US", theme: "AI", confidence: 0.75, notes: null })],
      }),
    ]);
  });

  it("renders the watchlist header, snapshot, and company table", async () => {
    renderWithQueryClient(<WatchlistDetailPage watchlistId="wl-1" />);

    expect(await screen.findByRole("heading", { name: "Tech Growth" })).toBeInTheDocument();
    const table = getTable();
    expect(within(table).getByText("AAPL")).toBeInTheDocument();
    expect(within(table).getByText("Technology")).toBeInTheDocument();
    expect(within(table).getByText("US")).toBeInTheDocument();
    expect(within(table).getByText("AI")).toBeInTheDocument();
    expect(within(table).getByText("75%")).toBeInTheDocument();
  });

  it("adds a company through the dialog", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WatchlistDetailPage watchlistId="wl-1" />);
    await waitFor(() => {
      expect(within(getTable()).getByText("AAPL")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Add company" }));
    const dialog = screen.getByRole("dialog", { name: "Add company" });
    await user.type(within(dialog).getByLabelText("Ticker"), "MSFT");
    await user.click(within(dialog).getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(within(getTable()).getByText("MSFT")).toBeInTheDocument();
    });
  });

  it("removes a company after confirming", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WatchlistDetailPage watchlistId="wl-1" />);
    await waitFor(() => {
      expect(within(getTable()).getByText("AAPL")).toBeInTheDocument();
    });

    await user.click(within(getTable()).getByRole("button", { name: "Remove" }));
    const dialog = screen.getByRole("dialog", { name: "Remove company" });
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));

    await waitFor(() => {
      expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    });
  });

  it("edits a company's notes inline, optimistically", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WatchlistDetailPage watchlistId="wl-1" />);
    await waitFor(() => {
      expect(within(getTable()).getByText("AAPL")).toBeInTheDocument();
    });

    await user.click(within(getTable()).getByRole("button", { name: "Edit notes for AAPL" }));
    const textarea = within(getTable()).getByLabelText("Notes for AAPL");
    await user.type(textarea, "Watching Q3 earnings");
    await user.click(within(getTable()).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(within(getTable()).getByText("Watching Q3 earnings")).toBeInTheDocument();
    });
  });

  it("shows the portfolio summary panel with real distribution data", async () => {
    renderWithQueryClient(<WatchlistDetailPage watchlistId="wl-1" />);

    expect(await screen.findByText("Sector distribution")).toBeInTheDocument();
  });

  it("shows an empty state when no risk assessment exists yet (404)", async () => {
    server.use(
      http.get(`${API_BASE_URL}/portfolio/risk`, () =>
        HttpResponse.json({ error: "not_found", message: "None yet.", meta: buildMeta() }, { status: 404 }),
      ),
    );
    renderWithQueryClient(<WatchlistDetailPage watchlistId="wl-1" />);

    expect(await screen.findByText("No risk assessment yet")).toBeInTheDocument();
  });

  it("shows recommendation availability with candidate counts when available", async () => {
    renderWithQueryClient(<WatchlistDetailPage watchlistId="wl-1" />);

    expect(await screen.findByText("Available")).toBeInTheDocument();
    expect(screen.getByText(/3 candidates/)).toBeInTheDocument();
  });

  it("shows an unavailable state when intelligence is not configured on the backend (503)", async () => {
    server.use(
      http.get(`${API_BASE_URL}/portfolio/intelligence`, () =>
        HttpResponse.json({ error: "service_unavailable", message: "Not configured.", meta: buildMeta() }, { status: 503 }),
      ),
    );
    renderWithQueryClient(<WatchlistDetailPage watchlistId="wl-1" />);

    expect(await screen.findByText("Portfolio intelligence unavailable")).toBeInTheDocument();
  });

  it("shows live market data attached to the portfolio intelligence report (Milestone 14)", async () => {
    renderWithQueryClient(<WatchlistDetailPage watchlistId="wl-1" />);

    expect(await screen.findByText("Live market data")).toBeInTheDocument();
    expect(screen.getByText("NFLX")).toBeInTheDocument();
    expect(screen.getByText("$610.25")).toBeInTheDocument();
    expect(screen.getByText("Fresh")).toBeInTheDocument();
    expect(screen.getByText(/1 fresh/)).toBeInTheDocument();
  });
});
