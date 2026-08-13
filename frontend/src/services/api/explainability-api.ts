import { apiClient } from "@/services/api/client";
import type { SuccessResponse } from "@/types/api";
import type { ExplainabilityResult, GenerateExplanationRequest } from "@/types/explainability";

/** Thin wrappers over `/api/v1/explainability/*`. */
export const explainabilityApi = {
  generate: async (body: GenerateExplanationRequest): Promise<ExplainabilityResult> => {
    const response = await apiClient.post<SuccessResponse<ExplainabilityResult>>("/explainability", body);
    return response.data;
  },

  get: async (requestId: string): Promise<ExplainabilityResult> => {
    const response = await apiClient.get<SuccessResponse<ExplainabilityResult>>(
      `/explainability/${encodeURIComponent(requestId)}`,
    );
    return response.data;
  },
};
