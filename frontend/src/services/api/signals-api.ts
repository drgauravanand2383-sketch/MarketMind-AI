import { apiClient } from "@/services/api/client";
import { buildQueryString } from "@/lib/query-string";
import type { PaginatedResponse, SuccessResponse } from "@/types/api";
import type { EvaluateSignalsRequest, ListSignalDefinitionsParams, SignalDefinition, SignalEvaluationEnvelope } from "@/types/signals";

/** Thin wrappers over `/api/v1/signals/*`. Definition CRUD beyond `list`
 * isn't wrapped here — this milestone only needs to browse existing
 * definitions to evaluate against, not author new ones. */
export const signalsApi = {
  listDefinitions: async (params: ListSignalDefinitionsParams = {}): Promise<PaginatedResponse<SignalDefinition>> => {
    return apiClient.get<PaginatedResponse<SignalDefinition>>(`/signals/definitions${buildQueryString(params)}`);
  },

  evaluate: async (body: EvaluateSignalsRequest): Promise<SignalEvaluationEnvelope> => {
    const response = await apiClient.post<SuccessResponse<SignalEvaluationEnvelope>>("/signals/evaluate", body);
    return response.data;
  },

  getResult: async (resultId: string): Promise<SignalEvaluationEnvelope> => {
    const response = await apiClient.get<SuccessResponse<SignalEvaluationEnvelope>>(
      `/signals/results/${encodeURIComponent(resultId)}`,
    );
    return response.data;
  },
};
