import { apiClient } from "@/services/api/client";
import { buildQueryString } from "@/lib/query-string";
import type { PaginatedResponse, SuccessResponse } from "@/types/api";
import type { Alert, AlertBatch, EvaluateAlertsRequest, ListAlertsParams } from "@/types/alerts";

/** Thin wrappers over `/api/v1/alerts/*`. There is no rule-CRUD or
 * rule-listing endpoint anywhere on the real backend — `evaluate` always
 * sends `rule_ids: []` ("every enabled rule") from this frontend; see
 * `@/types/alerts`'s module docstring. */
export const alertsApi = {
  list: async (params: ListAlertsParams = {}): Promise<PaginatedResponse<Alert>> => {
    return apiClient.get<PaginatedResponse<Alert>>(`/alerts${buildQueryString(params)}`);
  },

  get: async (alertId: string): Promise<Alert> => {
    const response = await apiClient.get<SuccessResponse<Alert>>(`/alerts/${encodeURIComponent(alertId)}`);
    return response.data;
  },

  evaluate: async (body: EvaluateAlertsRequest): Promise<AlertBatch> => {
    const response = await apiClient.post<SuccessResponse<AlertBatch>>("/alerts/evaluate", body);
    return response.data;
  },
};
