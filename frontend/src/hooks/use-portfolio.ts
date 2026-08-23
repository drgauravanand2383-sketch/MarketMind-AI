import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { portfolioApi } from "@/services/api/portfolio-api";
import { ApiError } from "@/services/api/errors";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { notify } from "@/store/notification-store";
import type { GenerateRecommendationsRequest } from "@/types/portfolio";

export const portfolioKeys = {
  summary: (portfolioId: string) => ["portfolio", "summary", portfolioId] as const,
  intelligence: (portfolioId: string) => ["portfolio", "intelligence", portfolioId] as const,
  risk: (portfolioId: string) => ["portfolio", "risk", portfolioId] as const,
  recommendations: (portfolioId: string) => ["portfolio", "recommendations", portfolioId] as const,
  analysisStatus: (portfolioId: string) => ["portfolio", "analysis-status", portfolioId] as const,
};

export function usePortfolioSummary(portfolioId: string) {
  return useQuery({
    queryKey: portfolioKeys.summary(portfolioId),
    queryFn: () => portfolioApi.getSummary(portfolioId),
    enabled: portfolioId.length > 0,
  });
}

export function usePortfolioIntelligence(portfolioId: string) {
  return useQuery({
    queryKey: portfolioKeys.intelligence(portfolioId),
    queryFn: () => portfolioApi.getIntelligence(portfolioId),
    enabled: portfolioId.length > 0,
    // A 503 (no ANTHROPIC_API_KEY configured) is a real, if expected,
    // failure — not a transient one worth retrying.
    retry: false,
  });
}

/** A `404` here means "no risk assessment exists yet for this
 * portfolio" — a normal, expected state, not a genuine error. Never
 * retried (retrying a 404 can't produce a different answer), and
 * exposed as `isUnavailable` so callers can render an empty state
 * instead of an error state for it. `GET /portfolio/risk` itself is
 * still GET-only/read-only (unchanged) — v1.2 Priority 8 added a way to
 * *trigger* the first assessment (`useTriggerInitialAnalysis` below), not
 * a way to fetch one differently; this remains the only risk-fetching
 * hook. */
export function usePortfolioRisk(portfolioId: string) {
  const query = useQuery({
    queryKey: portfolioKeys.risk(portfolioId),
    queryFn: () => portfolioApi.getRisk(portfolioId),
    enabled: portfolioId.length > 0,
    retry: false,
    // A 404 here is `isUnavailable`, not `isError` (see docstring above) —
    // the global error toast (`app/query-client.ts`) must not fire for it;
    // the panel already renders its own graceful empty state.
    meta: { suppressErrorToast: true },
  });
  const isUnavailable = query.error instanceof ApiError && query.error.status === 404;
  return { ...query, isUnavailable, isError: query.isError && !isUnavailable };
}

/** Same 404-means-unavailable convention as `usePortfolioRisk`. As of
 * Milestone 5 this is a full detail fetch (every `RecommendationCandidate`
 * field, not just availability) — `useGenerateRecommendations` below is
 * the mutation that produces a fresh result for this same query to pick up. */
export function usePortfolioRecommendations(portfolioId: string) {
  const query = useQuery({
    queryKey: portfolioKeys.recommendations(portfolioId),
    queryFn: () => portfolioApi.getRecommendations(portfolioId),
    enabled: portfolioId.length > 0,
    retry: false,
    // Same 404-is-`isUnavailable`-not-`isError` reasoning as `usePortfolioRisk` above.
    meta: { suppressErrorToast: true },
  });
  const isUnavailable = query.error instanceof ApiError && query.error.status === 404;
  return { ...query, isUnavailable, isError: query.isError && !isUnavailable };
}

const ANALYSIS_STATUS_POLL_INTERVAL_MS = 3_000;

/** v1.2 Priority 8. Polls every 3s only while `status === "ANALYZING"` —
 * the existing RECOMMENDATION_GENERATED/RISK_ASSESSMENT_COMPLETED
 * real-time events (`@/lib/realtime-invalidation`) already invalidate this
 * query the moment a job actually finishes, so polling here is only a
 * fallback for a client that missed the WS event (reconnect gap, tab was
 * backgrounded) — never the primary update mechanism. */
export function useInitialAnalysisStatus(portfolioId: string) {
  return useQuery({
    queryKey: portfolioKeys.analysisStatus(portfolioId),
    queryFn: () => portfolioApi.getAnalysisStatus(portfolioId),
    enabled: portfolioId.length > 0,
    refetchInterval: (query) => (query.state.data?.status === "ANALYZING" ? ANALYSIS_STATUS_POLL_INTERVAL_MS : false),
  });
}

/** v1.2 Priority 8. The one supported way to retry after a prior attempt
 * ended in `ERROR` — also safe to call when analysis is already
 * READY/PARTIAL/ANALYZING (the backend job is itself idempotent). */
export function useTriggerInitialAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (portfolioId: string) => portfolioApi.triggerAnalysis(portfolioId),
    onSuccess: (state, portfolioId) => {
      queryClient.setQueryData(portfolioKeys.analysisStatus(portfolioId), state);
    },
    onSettled: (_state, _error, portfolioId) => {
      void queryClient.invalidateQueries({ queryKey: portfolioKeys.analysisStatus(portfolioId) });
    },
  });
}

/** Deliberately **not optimistic** (explicit Milestone 5 instruction:
 * "Do NOT optimistically update recommendation data") — the UI waits for
 * the real, server-computed `RecommendationResult` rather than guessing
 * at scores/types the engine hasn't actually produced yet. */
export function useGenerateRecommendations() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: GenerateRecommendationsRequest) => portfolioApi.generateRecommendations(body),
    onSuccess: (result, body) => {
      queryClient.setQueryData(portfolioKeys.recommendations(body.portfolio_id), result);
      notify("success", `Recommendations generated — ${String(result.total_candidates)} candidates scored.`);
      useDecisionHistoryStore.getState().addEntry({
        kind: "recommendations_generated",
        id: result.request_id,
        portfolioId: body.portfolio_id,
        requestId: result.request_id,
        candidateCount: result.total_candidates,
        occurredAt: result.generated_at,
      });
    },
    onSettled: (_result, _error, body) => {
      void queryClient.invalidateQueries({ queryKey: portfolioKeys.recommendations(body.portfolio_id) });
    },
  });
}
