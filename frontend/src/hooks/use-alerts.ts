import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { alertsApi } from "@/services/api/alerts-api";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { notify } from "@/store/notification-store";
import type { EvaluateAlertsRequest, ListAlertsParams } from "@/types/alerts";

export const alertsKeys = {
  lists: () => ["alerts", "list"] as const,
  list: (params: ListAlertsParams) => [...alertsKeys.lists(), params] as const,
  detail: (id: string) => ["alerts", "detail", id] as const,
};

export function useAlertsList(params: ListAlertsParams) {
  return useQuery({
    queryKey: alertsKeys.list(params),
    queryFn: () => alertsApi.list(params),
    placeholderData: (previous) => previous,
  });
}

export function useAlert(alertId: string) {
  return useQuery({
    queryKey: alertsKeys.detail(alertId),
    queryFn: () => alertsApi.get(alertId),
    enabled: alertId.length > 0,
  });
}

/** No WebSocket event is awaited here — `ALERT_GENERATED` is published
 * server-side as a result of this same call, not something the frontend
 * needs to separately subscribe to for this synchronous request/response
 * flow. `isPending` is the loading indicator. */
export function useEvaluateAlerts() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: EvaluateAlertsRequest) => alertsApi.evaluate(body),
    onSuccess: (batch) => {
      void queryClient.invalidateQueries({ queryKey: alertsKeys.lists() });
      notify("success", `Alert evaluation complete — ${String(batch.generated)} generated, ${String(batch.suppressed)} suppressed.`);
      useDecisionHistoryStore.getState().addEntry({
        kind: "alerts_evaluated",
        id: crypto.randomUUID(),
        generatedCount: batch.generated,
        suppressedCount: batch.suppressed,
        occurredAt: new Date().toISOString(),
      });
    },
  });
}
