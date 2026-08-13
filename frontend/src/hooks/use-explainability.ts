import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { explainabilityApi } from "@/services/api/explainability-api";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { notify } from "@/store/notification-store";
import type { GenerateExplanationRequest } from "@/types/explainability";

export const explainabilityKeys = {
  results: () => ["explainability", "results"] as const,
  result: (requestId: string) => [...explainabilityKeys.results(), requestId] as const,
};

/** `POST /explainability` creates the request and generates the
 * explanation fully synchronously in one call — `isPending` is the
 * loading indicator. */
export function useGenerateExplanation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: GenerateExplanationRequest) => explainabilityApi.generate(body),
    onSuccess: (result, body) => {
      queryClient.setQueryData(explainabilityKeys.result(result.request_id), result);
      notify("success", "Explainability report generated.");
      useDecisionHistoryStore.getState().addEntry({
        kind: "explainability_generated",
        id: result.request_id,
        requestId: result.request_id,
        recommendationResultId: body.recommendation_result_id,
        occurredAt: result.generated_at,
      });
    },
  });
}

export function useExplainabilityResult(requestId: string) {
  return useQuery({
    queryKey: explainabilityKeys.result(requestId),
    queryFn: () => explainabilityApi.get(requestId),
    enabled: requestId.length > 0,
  });
}
