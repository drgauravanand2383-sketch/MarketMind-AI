import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { buildMeta } from "@/test/msw/fixtures";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { queryClient } from "@/app/query-client";
import { API_BASE_URL } from "@/services/api/config";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { useNotificationStore } from "@/store/notification-store";
import { buildInitialAnalysisState } from "@/test/msw/fixtures";
import {
  useGenerateRecommendations,
  useInitialAnalysisStatus,
  usePortfolioIntelligence,
  usePortfolioRecommendations,
  usePortfolioRisk,
  useTriggerInitialAnalysis,
} from "@/hooks/use-portfolio";

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

  describe("v1.2 Priority 8 — initial analysis status/trigger", () => {
    it("useInitialAnalysisStatus returns the status for an existing portfolio", async () => {
      server.use(
        http.get(`${API_BASE_URL}/portfolio/wl-1/analysis-status`, () =>
          HttpResponse.json({ data: buildInitialAnalysisState({ status: "PARTIAL" }), meta: buildMeta() }),
        ),
      );
      const { result } = renderHookWithQueryClient(() => useInitialAnalysisStatus("wl-1"));

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });
      expect(result.current.data?.status).toBe("PARTIAL");
    });

    it("useInitialAnalysisStatus polls while ANALYZING and stops once settled", async () => {
      let callCount = 0;
      server.use(
        http.get(`${API_BASE_URL}/portfolio/wl-1/analysis-status`, () => {
          callCount += 1;
          const status = callCount < 2 ? "ANALYZING" : "READY";
          return HttpResponse.json({ data: buildInitialAnalysisState({ status }), meta: buildMeta() });
        }),
      );
      const { result } = renderHookWithQueryClient(() => useInitialAnalysisStatus("wl-1"));

      await waitFor(
        () => {
          expect(result.current.data?.status).toBe("READY");
        },
        { timeout: 10_000 },
      );
      expect(callCount).toBeGreaterThanOrEqual(2);
    });

    it("useTriggerInitialAnalysis posts to the trigger endpoint and seeds the status cache", async () => {
      server.use(
        http.post(`${API_BASE_URL}/portfolio/wl-1/analysis`, () =>
          HttpResponse.json(
            { data: buildInitialAnalysisState({ status: "ANALYZING" }), meta: buildMeta() },
            { status: 202 },
          ),
        ),
      );
      const { result, queryClient: hookQueryClient } = renderHookWithQueryClient(() => useTriggerInitialAnalysis());

      result.current.mutate("wl-1");

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });
      expect(hookQueryClient.getQueryData(["portfolio", "analysis-status", "wl-1"])).toMatchObject({
        status: "ANALYZING",
      });
    });
  });

  // These render through the app's real `queryClient` singleton
  // (`app/query-client.ts`), not the isolated per-test client the suite
  // otherwise uses — only that singleton carries the global
  // `QueryCache`/`MutationCache` `onError` toast wiring (`notifyApiError`),
  // so it's the only way to actually exercise (and regression-guard) the
  // `meta: { suppressErrorToast: true }` fix below.
  describe("global error-toast suppression for expected 404s", () => {
    beforeEach(() => {
      queryClient.clear();
    });

    it("usePortfolioRisk does not show the global error toast for an expected 404", async () => {
      server.use(
        http.get(`${API_BASE_URL}/portfolio/risk`, () =>
          HttpResponse.json({ error: "not_found", message: "Not found.", meta: buildMeta() }, { status: 404 }),
        ),
      );
      const { result } = renderHookWithQueryClient(() => usePortfolioRisk("wl-1"), queryClient);

      await waitFor(() => {
        expect(result.current.isUnavailable).toBe(true);
      });
      expect(result.current.isError).toBe(false);
      expect(useNotificationStore.getState().notifications).toHaveLength(0);
    });

    it("usePortfolioRecommendations does not show the global error toast for an expected 404", async () => {
      server.use(
        http.get(`${API_BASE_URL}/portfolio/recommendations`, () =>
          HttpResponse.json({ error: "not_found", message: "Not found.", meta: buildMeta() }, { status: 404 }),
        ),
      );
      const { result } = renderHookWithQueryClient(() => usePortfolioRecommendations("wl-1"), queryClient);

      await waitFor(() => {
        expect(result.current.isUnavailable).toBe(true);
      });
      expect(result.current.isError).toBe(false);
      expect(useNotificationStore.getState().notifications).toHaveLength(0);
    });

    it("an unrelated query (usePortfolioIntelligence) still shows the global error toast for a genuinely unexpected error", async () => {
      // Proves the suppression is scoped to exactly the two touched hooks
      // (`meta: { suppressErrorToast: true }` added only to `usePortfolioRisk`/
      // `usePortfolioRecommendations`) — every other query's errors, including
      // a genuine 500 from a sibling portfolio endpoint, still surface the
      // global toast exactly as before. `usePortfolioIntelligence` already
      // sets `retry: false` (unrelated to this fix), so the failure — and
      // the toast it triggers — is deterministic and fast.
      server.use(
        http.get(`${API_BASE_URL}/portfolio/intelligence`, () =>
          HttpResponse.json({ error: "internal_error", message: "Something broke.", meta: buildMeta() }, { status: 500 }),
        ),
      );
      const { result } = renderHookWithQueryClient(() => usePortfolioIntelligence("wl-1"), queryClient);

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
      await waitFor(() => {
        expect(useNotificationStore.getState().notifications).toHaveLength(1);
      });
      expect(useNotificationStore.getState().notifications[0]?.message).toBe("Something broke.");
    });
  });
});
