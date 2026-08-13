import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { signalsApi } from "@/services/api/signals-api";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import type { EvaluateSignalsRequest, ListSignalDefinitionsParams } from "@/types/signals";

export const signalsKeys = {
  definitionLists: () => ["signals", "definitions"] as const,
  definitionList: (params: ListSignalDefinitionsParams) => [...signalsKeys.definitionLists(), params] as const,
  results: () => ["signals", "results"] as const,
  result: (id: string) => [...signalsKeys.results(), id] as const,
};

export function useSignalDefinitionsList(params: ListSignalDefinitionsParams) {
  return useQuery({
    queryKey: signalsKeys.definitionList(params),
    queryFn: () => signalsApi.listDefinitions(params),
  });
}

/** No WebSocket event drives signal-evaluation progress — the mutation's
 * own `isPending` is the loading indicator (Milestone 4 convention). */
export function useEvaluateSignals() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: EvaluateSignalsRequest) => signalsApi.evaluate(body),
    onSuccess: (envelope) => {
      queryClient.setQueryData(signalsKeys.result(envelope.result_id), envelope);
      useDecisionHistoryStore.getState().addEntry({
        kind: "signals_evaluated",
        id: envelope.result_id,
        resultId: envelope.result_id,
        definitionId: envelope.definition_id,
        triggeredCount: envelope.batch_result.triggered,
        occurredAt: new Date().toISOString(),
      });
    },
  });
}

/** `result_id` only resolves against the same backend process that
 * cached it (in-memory store) — a 404 means "no longer available." */
export function useSignalResult(resultId: string) {
  return useQuery({
    queryKey: signalsKeys.result(resultId),
    queryFn: () => signalsApi.getResult(resultId),
    enabled: resultId.length > 0,
  });
}
