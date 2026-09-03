import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import type * as ReactRouterModule from "@tanstack/react-router";
import { TodaysGlobalMarketsCard } from "@/features/dashboard/todays-global-markets-card";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildIntelligenceRun, buildNormalizedAssetSnapshot, buildRankedAsset } from "@/test/msw/fixtures";
import { resetGlobalMarketsStore, seedRankedAssets, seedRun } from "@/test/msw/global-markets-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: ({ to, children }: { to: string; children?: ReactNode }) => <a href={to}>{children}</a> };
});

describe("TodaysGlobalMarketsCard", () => {
  beforeEach(() => {
    resetGlobalMarketsStore();
  });

  it("shows an empty state with a report link when no run has ever completed", async () => {
    renderWithQueryClient(<TodaysGlobalMarketsCard />);

    expect(await screen.findByText("No intelligence run yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view full report/i })).toHaveAttribute("href", "/global-markets");
  });

  it("surfaces the latest run's status, IST time, and a top-3 preview per segment", async () => {
    seedRun(
      buildIntelligenceRun({ id: "run-1", run_date: "2026-02-01", status: "COMPLETED", completed_at: "2026-02-01T03:05:00Z" }),
    );
    seedRankedAssets("run-1", "INDIA_EQUITY", [
      buildRankedAsset({ rank: 1, snapshot: buildNormalizedAssetSnapshot({ ticker: "RELIANCE" }) }),
      buildRankedAsset({ rank: 2, snapshot: buildNormalizedAssetSnapshot({ ticker: "TCS" }) }),
      buildRankedAsset({ rank: 3, snapshot: buildNormalizedAssetSnapshot({ ticker: "HDFCBANK" }) }),
      buildRankedAsset({ rank: 4, snapshot: buildNormalizedAssetSnapshot({ ticker: "INFY" }) }),
    ]);

    renderWithQueryClient(<TodaysGlobalMarketsCard />);

    // Preview is depth-3 — the 4th-ranked name is not shown.
    expect(await screen.findByText("RELIANCE, TCS, HDFCBANK")).toBeInTheDocument();
    expect(screen.getByText("Run date 2026-02-01")).toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByText(/generated .*IST/i)).toBeInTheDocument();
    expect(screen.queryByText(/INFY/)).not.toBeInTheDocument();
  });

  it("flags a stale run whose run date is several days old", async () => {
    const staleDate = new Date(Date.now() - 5 * 86_400_000).toISOString().slice(0, 10);
    seedRun(buildIntelligenceRun({ id: "run-old", run_date: staleDate, status: "COMPLETED" }));
    seedRankedAssets("run-old", "INDIA_EQUITY", [buildRankedAsset({ snapshot: buildNormalizedAssetSnapshot({ ticker: "RELIANCE" }) })]);

    renderWithQueryClient(<TodaysGlobalMarketsCard />);

    expect(await screen.findByText(/Last run was 5 days ago/)).toBeInTheDocument();
  });
});
