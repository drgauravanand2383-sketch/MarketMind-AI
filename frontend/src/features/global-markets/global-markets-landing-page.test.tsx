import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GlobalMarketsLandingPage } from "@/features/global-markets/global-markets-landing-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildCategoryIntelligenceReport, buildIntelligenceRun, buildNormalizedAssetSnapshot, buildRankedAsset } from "@/test/msw/fixtures";
import { resetGlobalMarketsStore, seedRankedAssets, seedReport, seedRun } from "@/test/msw/global-markets-store";
import { useGlobalMarketsStore } from "@/store/global-markets-store";

describe("GlobalMarketsLandingPage", () => {
  beforeEach(() => {
    resetGlobalMarketsStore();
    useGlobalMarketsStore.setState({ activeTab: "INDIA_EQUITY", activePennySubTab: "INDIA_PENNY_STOCK" });
  });

  it("shows an empty state when no run has ever completed", async () => {
    renderWithQueryClient(<GlobalMarketsLandingPage />);

    expect(await screen.findByText("No intelligence run yet")).toBeInTheDocument();
  });

  it("renders the latest run's status and the default (India Stocks) tab's ranked assets", async () => {
    seedRun(buildIntelligenceRun({ id: "run-1", run_date: "2026-02-01", status: "COMPLETED" }));
    seedRankedAssets("run-1", "INDIA_EQUITY", [
      buildRankedAsset({ rank: 1, snapshot: buildNormalizedAssetSnapshot({ ticker: "RELIANCE", name: "Reliance Industries" }) }),
      buildRankedAsset({ rank: 2, snapshot: buildNormalizedAssetSnapshot({ ticker: "TCS", name: "Tata Consultancy" }) }),
    ]);

    renderWithQueryClient(<GlobalMarketsLandingPage />);

    expect(await screen.findByText("RELIANCE")).toBeInTheDocument();
    expect(screen.getByText("TCS")).toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByText("Run date 2026-02-01")).toBeInTheDocument();
  });

  it("switching tabs fetches and renders that category's own ranked assets", async () => {
    seedRun(buildIntelligenceRun({ id: "run-1", status: "COMPLETED" }));
    seedRankedAssets("run-1", "INDIA_EQUITY", [buildRankedAsset({ snapshot: buildNormalizedAssetSnapshot({ ticker: "RELIANCE" }) })]);
    seedRankedAssets("run-1", "US_EQUITY", [
      buildRankedAsset({ category: "US_EQUITY", snapshot: buildNormalizedAssetSnapshot({ ticker: "AAPL", report_category: "US_EQUITY", currency: "USD" }) }),
    ]);

    renderWithQueryClient(<GlobalMarketsLandingPage />);
    await screen.findByText("RELIANCE");

    await userEvent.click(screen.getByRole("tab", { name: "US Stocks" }));

    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("RELIANCE")).not.toBeInTheDocument();
  });

  it("the Penny & Micro-Cap tab shows its own sub-tabs, defaulting to India Penny Stocks", async () => {
    seedRun(buildIntelligenceRun({ id: "run-1", status: "COMPLETED" }));
    seedRankedAssets("run-1", "INDIA_PENNY_STOCK", [
      buildRankedAsset({
        category: "INDIA_PENNY_STOCK",
        snapshot: buildNormalizedAssetSnapshot({ ticker: "PENNYCO", report_category: "INDIA_PENNY_STOCK" }),
        risk_classification: "STRONG_MOMENTUM_HIGH_RISK",
      }),
    ]);

    renderWithQueryClient(<GlobalMarketsLandingPage />);

    await userEvent.click(await screen.findByRole("tab", { name: "Penny & Micro-Cap" }));

    expect(await screen.findByRole("tab", { name: "India Penny Stocks" })).toBeInTheDocument();
    expect(await screen.findByText("PENNYCO")).toBeInTheDocument();
    expect(screen.getByText("Strong momentum, high risk")).toBeInTheDocument();
  });

  it("shows a partial-run banner naming the categories that failed to generate", async () => {
    seedRun(
      buildIntelligenceRun({
        id: "run-1",
        status: "PARTIAL",
        category_outcomes: [
          { category: "INDIA_EQUITY", succeeded: true, market_session_context: null, error: null },
          { category: "US_EQUITY", succeeded: false, market_session_context: null, error: "provider unavailable" },
        ],
      }),
    );
    seedRankedAssets("run-1", "INDIA_EQUITY", [buildRankedAsset({ snapshot: buildNormalizedAssetSnapshot({ ticker: "RELIANCE" }) })]);

    renderWithQueryClient(<GlobalMarketsLandingPage />);

    await waitFor(() => {
      expect(screen.getByText("PARTIAL")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toHaveTextContent("1 of 2 categories failed to generate in this run: US Stocks.");
  });

  it("shows a data freshness badge for the active category", async () => {
    seedRun(buildIntelligenceRun({ id: "run-1", status: "COMPLETED" }));
    seedRankedAssets("run-1", "INDIA_EQUITY", [buildRankedAsset({ snapshot: buildNormalizedAssetSnapshot({ ticker: "RELIANCE" }) })]);

    renderWithQueryClient(<GlobalMarketsLandingPage />);

    expect(await screen.findByText("RELIANCE")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("shows the real failure reason for a category that failed to generate", async () => {
    seedRun(
      buildIntelligenceRun({
        id: "run-1",
        status: "PARTIAL",
        category_outcomes: [
          { category: "INDIA_EQUITY", succeeded: false, market_session_context: null, error: "provider unavailable" },
        ],
      }),
    );

    renderWithQueryClient(<GlobalMarketsLandingPage />);

    expect(await screen.findByText("India Stocks failed to generate in this run")).toBeInTheDocument();
    expect(screen.getByText("provider unavailable")).toBeInTheDocument();
  });

  it("expanding a ranked asset's row shows its factor-score breakdown and per-asset commentary", async () => {
    seedRun(buildIntelligenceRun({ id: "run-1", status: "COMPLETED" }));
    seedRankedAssets("run-1", "INDIA_EQUITY", [
      buildRankedAsset({
        snapshot: buildNormalizedAssetSnapshot({ ticker: "RELIANCE" }),
        factor_scores: [{ factor: "MOMENTUM", value: 82, explanation: "Strong 15D trend." }],
      }),
    ]);
    seedReport(
      buildCategoryIntelligenceReport({
        run_id: "run-1",
        category: "INDIA_EQUITY",
        asset_commentaries: [{ ticker: "RELIANCE", rank: 1, commentary: "Consistent volume backing the move." }],
      }),
    );

    renderWithQueryClient(<GlobalMarketsLandingPage />);
    await screen.findByText("RELIANCE");

    expect(screen.queryByText("Consistent volume backing the move.")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(screen.getByText("Momentum")).toBeInTheDocument();
    expect(screen.getByText("Strong 15D trend.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Consistent volume backing the move.")).toBeInTheDocument();
    // Asset-level freshness (independent of the category-level badge).
    expect(screen.getAllByText("Live").length).toBeGreaterThan(1);
  });

  it("the run picker lets the user switch to a past run, showing a clear 'not the latest' indicator", async () => {
    seedRun(buildIntelligenceRun({ id: "run-2", run_date: "2026-01-31", status: "COMPLETED" }));
    seedRun(buildIntelligenceRun({ id: "run-1", run_date: "2026-02-01", status: "COMPLETED" })); // seeded last -> latest
    seedRankedAssets("run-1", "INDIA_EQUITY", [buildRankedAsset({ snapshot: buildNormalizedAssetSnapshot({ ticker: "RELIANCE" }) })]);
    seedRankedAssets("run-2", "INDIA_EQUITY", [buildRankedAsset({ snapshot: buildNormalizedAssetSnapshot({ ticker: "OLDTICKER" }) })]);

    renderWithQueryClient(<GlobalMarketsLandingPage />);
    expect(await screen.findByText("RELIANCE")).toBeInTheDocument();
    expect(screen.queryByText(/Viewing the persisted snapshot/)).not.toBeInTheDocument();

    const picker = await screen.findByLabelText("Run");
    await userEvent.selectOptions(picker, "run-2");

    expect(await screen.findByText("OLDTICKER")).toBeInTheDocument();
    expect(screen.queryByText("RELIANCE")).not.toBeInTheDocument();
    expect(screen.getByText(/Viewing the persisted snapshot from 2026-01-31/)).toBeInTheDocument();
  });
});
