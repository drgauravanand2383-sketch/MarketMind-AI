import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { RiskPanel } from "@/features/decision-center/risk/risk-panel";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildMeta } from "@/test/msw/fixtures";
import { server } from "@/test/msw/server";
import { API_BASE_URL } from "@/services/api/config";
import { useNotificationStore } from "@/store/notification-store";

describe("RiskPanel", () => {
  beforeEach(() => {
    useNotificationStore.setState({ notifications: [] });
  });

  it("prompts for a portfolio when none is selected", () => {
    renderWithQueryClient(<RiskPanel portfolioId="" />);
    expect(screen.getByText("Select a portfolio")).toBeInTheDocument();
  });

  it("renders the overall score/severity, exposures, and derived category scores", async () => {
    renderWithQueryClient(<RiskPanel portfolioId="wl-1" />);

    await waitFor(() => {
      expect(screen.getByText("42")).toBeInTheDocument();
    });
    expect(screen.getAllByText("MODERATE").length).toBeGreaterThan(0);
    expect(screen.getByText("Diversification")).toBeInTheDocument();
    expect(screen.getByText("Concentration")).toBeInTheDocument();
    expect(screen.getByText("Liquidity")).toBeInTheDocument();
    expect(screen.getByText("Volatility")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Risk category breakdown" })).toBeInTheDocument();
    // "Sector exposure"/"Country exposure" appear twice each — once as the
    // chart panel's own title, once as the plain-list panel's title below it.
    expect(screen.getAllByRole("heading", { name: "Sector exposure" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("heading", { name: "Country exposure" }).length).toBeGreaterThan(0);
  });

  it("fires the 'Risk loaded' notification exactly once for the same assessment", async () => {
    renderWithQueryClient(<RiskPanel portfolioId="wl-1" />);

    await waitFor(() => {
      expect(useNotificationStore.getState().notifications.some((n) => /Risk assessment loaded/i.test(n.message))).toBe(true);
    });
    const matchCount = useNotificationStore.getState().notifications.filter((n) => /Risk assessment loaded/i.test(n.message)).length;
    expect(matchCount).toBe(1);
  });

  it("shows the market-data-coverage indicator on the overall risk card (Milestone 14)", async () => {
    renderWithQueryClient(<RiskPanel portfolioId="wl-1" />);

    await waitFor(() => {
      expect(screen.getByText("42")).toBeInTheDocument();
    });
    expect(screen.getByText("Live market data: partial coverage")).toBeInTheDocument();
  });

  it("shows an unavailable empty state for a portfolio with no risk assessment yet", async () => {
    server.use(
      http.get(`${API_BASE_URL}/portfolio/risk`, () =>
        HttpResponse.json({ error: "not_found", message: "Not found.", meta: buildMeta() }, { status: 404 }),
      ),
    );
    renderWithQueryClient(<RiskPanel portfolioId="wl-1" />);

    expect(await screen.findByText("No risk assessment yet")).toBeInTheDocument();
  });
});
