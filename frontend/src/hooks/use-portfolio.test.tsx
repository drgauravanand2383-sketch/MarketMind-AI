import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { buildMeta } from "@/test/msw/fixtures";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { API_BASE_URL } from "@/services/api/config";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { useNotificationStore } from "@/store/notification-store";
import { useGenerateRecommendations, usePortfolioRecommendations, usePortfolioRisk } from "@/hooks/use-portfolio";

describe("use-portfolio (Milestone 5 additions)", () => {
  beforeEach(() => {
    useNotificationStore.setState({ notifications: [] });
    useDecisionHistoryStore.setState({ entries: [] });
  });

  it("usePortfolioRisk exposes isUnavailable for a 404 (no assessment yet)", async () => {
    server.use(
      http.get(`${API_BASE_URL}/portfolio/risk`, () =>
        HttpResponse.json({ error: "not_found", message: "Not found.", meta: buildMeta() }, { status: 404 }),
      ),
    );
    const { result } = renderHookWithQueryClient(() => usePortfolioRisk("wl-1"));

    await waitFor(() => {
      expect(result.current.isUnavailable).toBe(true);
    });
    expect(result.current.isError).toBe(false);
  });

  it("usePortfolioRisk returns the full assessment on success", async () => {
    const { result } = renderHookWithQueryClient(() => usePortfolioRisk("wl-1"));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.overall_risk_score).toBeGreaterThan(0);
    expect(result.current.data?.risk_metrics.length).toBeGreaterThan(0);
  });

  it("usePortfolioRecommendations returns real candidates as of Milestone 5", async () => {
    const { result } = renderHookWithQueryClient(() => usePortfolioRecommendations("wl-1"));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.recommendations.length).toBeGreaterThan(0);
    // Confidence is on a 0-100 scale, not 0-1 (a real gap the fixture used to get wrong).
    expect(result.current.data?.summary.average_confidence).toBeGreaterThan(1);
  });

  it("useGenerateRecommendations posts evidence and is not optimistic — data only appears after the server responds", async () => {
    const { result } = renderHookWithQueryClient(() => useGenerateRecommendations());

    expect(result.current.data).toBeUndefined();

    result.current.mutate({ portfolio_id: "wl-1", evidence: [{ ticker: "AAPL", company_name: "Apple Inc." }] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.recommendations).toHaveLength(1);
    expect(result.current.data?.recommendations[0]?.ticker).toBe("AAPL");
  });

  it("useGenerateRecommendations records a decision-history entry and shows a notification", async () => {
    const { result } = renderHookWithQueryClient(() => useGenerateRecommendations());

    result.current.mutate({ portfolio_id: "wl-1", evidence: [{ ticker: "AAPL" }] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(useDecisionHistoryStore.getState().entries).toHaveLength(1);
    expect(useDecisionHistoryStore.getState().entries[0]?.kind).toBe("recommendations_generated");
    expect(useNotificationStore.getState().notifications.some((n) => /generated/i.test(n.message))).toBe(true);
  });
});
