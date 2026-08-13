import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CompanyTable, type CompanyTableProps } from "@/features/watchlists/company-table";
import { buildWatchlistItem } from "@/test/msw/fixtures";

function baseProps(): CompanyTableProps {
  return {
    items: [buildWatchlistItem({ ticker: "AAPL", sector: "Technology", country: "US", theme: "AI", confidence: 0.75, notes: null })],
    onRemove: () => undefined,
    onSaveNotes: () => undefined,
    removingTicker: null,
    savingNotesTicker: null,
  };
}

/** Stubs `window.matchMedia` (jsdom has none) so `useMediaQuery` resolves
 * deterministically instead of falling back to its "desktop" default. */
function stubMatchMedia(matches: boolean): void {
  window.matchMedia = ((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

describe("CompanyTable", () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it("shows an empty state when there are no items", () => {
    render(<CompanyTable {...baseProps()} items={[]} />);
    expect(screen.getByText("No companies yet")).toBeInTheDocument();
  });

  describe("desktop viewport (>= 640px)", () => {
    beforeEach(() => {
      stubMatchMedia(true);
    });

    it("renders exactly one representation — a table, not a card list", () => {
      render(<CompanyTable {...baseProps()} />);

      expect(screen.getByRole("table", { name: "Companies in this watchlist" })).toBeInTheDocument();
      expect(screen.queryByRole("list")).not.toBeInTheDocument();
      expect(screen.getAllByText("AAPL")).toHaveLength(1);
    });
  });

  describe("mobile viewport (< 640px)", () => {
    beforeEach(() => {
      stubMatchMedia(false);
    });

    it("renders exactly one representation — a card list, not a table", () => {
      render(<CompanyTable {...baseProps()} />);

      expect(screen.queryByRole("table")).not.toBeInTheDocument();
      expect(screen.getByRole("list")).toBeInTheDocument();
      expect(screen.getAllByText("AAPL")).toHaveLength(1);
    });

    it("still exposes the same remove action from the card layout", async () => {
      const onRemove = vi.fn();
      render(<CompanyTable {...baseProps()} onRemove={onRemove} />);

      screen.getByRole("button", { name: "Remove" }).click();

      expect(onRemove).toHaveBeenCalledWith("AAPL");
    });
  });
});
