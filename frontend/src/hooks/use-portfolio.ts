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
 * instead of an error state for it. There is no `POST` anywhere to
 * trigger a new risk assessment (`docs/architecture/INTELLIGENCE_API.md`
 * — the REST surface for Risk is GET-only) — this is the only risk hook
 * that will ever exist. */
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
