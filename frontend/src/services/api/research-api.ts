import { apiClient } from "@/services/api/client";
import type { SuccessResponse } from "@/types/api";
import type {
  BatchCompanyResearchRequest,
  CompanyResearchReportEnvelope,
  CompanyResearchRequest,
} from "@/types/research";

/** Thin wrappers over `/api/v1/research/*`. There is no list/search
 * endpoint — `run`/`runBatch` are the only way to produce a report, and
 * `get` only works for a `request_id` returned by one of them, valid
 * only against the backend process that issued it (in-memory cache,
 * see `docs/architecture/INTELLIGENCE_API.md` §2). */
export const researchApi = {
  run: async (body: CompanyResearchRequest): Promise<CompanyResearchReportEnvelope> => {
    const response = await apiClient.post<SuccessResponse<CompanyResearchReportEnvelope>>("/research/company", body);
    return response.data;
  },

  runBatch: async (body: BatchCompanyResearchRequest): Promise<CompanyResearchReportEnvelope[]> => {
    const response = await apiClient.post<SuccessResponse<CompanyResearchReportEnvelope[]>>(
      "/research/batch",
      body,
    );
    return response.data;
  },

  get: async (requestId: string): Promise<CompanyResearchReportEnvelope> => {
    const response = await apiClient.get<SuccessResponse<CompanyResearchReportEnvelope>>(
      `/research/${encodeURIComponent(requestId)}`,
    );
    return response.data;
  },
};
