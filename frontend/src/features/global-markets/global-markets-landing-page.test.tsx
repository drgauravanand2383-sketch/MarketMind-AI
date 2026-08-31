import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GlobalMarketsLandingPage } from "@/features/global-markets/global-markets-landing-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildIntelligenceRun, buildNormalizedAssetSnapshot, buildRankedAsset } from "@/test/msw/fixtures";
import { resetGlobalMarketsStore, seedRankedAssets, seedRun } from "@/test/msw/global-markets-store";
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
          { category: "INDIA_EQUITY", succeeded: true, error: null },
          { category: "US_EQUITY", succeeded: false, error: "provider unavailable" },
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
});
