import { apiClient } from "@/services/api/client";
import type { SuccessResponse } from "@/types/api";
import type { ApplicationHealth, ReadinessStatus, VersionResponse } from "@/types/health";

/** Thin wrappers over the read-only system endpoints
 * (`GET /health`, `/ready`, `/version`) — the only backend calls this
 * milestone's Health Dashboard needs. */
export const systemApi = {
  getHealth: async (): Promise<ApplicationHealth> => {
    const response = await apiClient.get<SuccessResponse<ApplicationHealth>>("/health", { skipAuth: true });
    return response.data;
  },

  getReadiness: async (): Promise<ReadinessStatus> => {
    const response = await apiClient.get<SuccessResponse<ReadinessStatus>>("/ready", { skipAuth: true, skipRetry: true });
    return response.data;
  },

  getVersion: async (): Promise<VersionResponse> => {
    const response = await apiClient.get<SuccessResponse<VersionResponse>>("/version", { skipAuth: true });
    return response.data;
  },
};
