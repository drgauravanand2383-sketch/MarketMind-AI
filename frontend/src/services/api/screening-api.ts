import { apiClient } from "@/services/api/client";
import { buildQueryString } from "@/lib/query-string";
import type { PaginatedResponse, SuccessResponse } from "@/types/api";
import type {
  CreateScreeningProfileRequest,
  DuplicateScreeningProfileRequest,
  ListScreeningProfilesParams,
  RunScreeningRequest,
  ScreeningProfile,
  ScreeningRunEnvelope,
  UpdateScreeningProfileRequest,
} from "@/types/screening";

/** Thin wrappers over `/api/v1/screening/*`. Profiles are durably
 * persisted and support server-side name search/sort/pagination; run
 * results are cached in-memory only and addressable solely by the
 * `result_id` returned from `run` (lost on backend restart). */
export const screeningApi = {
  listProfiles: async (params: ListScreeningProfilesParams = {}): Promise<PaginatedResponse<ScreeningProfile>> => {
    return apiClient.get<PaginatedResponse<ScreeningProfile>>(`/screening/profiles${buildQueryString(params)}`);
  },

  getProfile: async (profileId: string): Promise<ScreeningProfile> => {
    const response = await apiClient.get<SuccessResponse<ScreeningProfile>>(
      `/screening/profiles/${encodeURIComponent(profileId)}`,
    );
    return response.data;
  },

  createProfile: async (body: CreateScreeningProfileRequest): Promise<ScreeningProfile> => {
    const response = await apiClient.post<SuccessResponse<ScreeningProfile>>("/screening/profiles", body);
    return response.data;
  },

  updateProfile: async (profileId: string, body: UpdateScreeningProfileRequest): Promise<ScreeningProfile> => {
    const response = await apiClient.patch<SuccessResponse<ScreeningProfile>>(
      `/screening/profiles/${encodeURIComponent(profileId)}`,
      body,
    );
    return response.data;
  },

  /** Frontend Milestone 4 addition — `POST /profiles/{id}/duplicate`. */
  duplicateProfile: async (
    profileId: string,
    body: DuplicateScreeningProfileRequest,
  ): Promise<ScreeningProfile> => {
    const response = await apiClient.post<SuccessResponse<ScreeningProfile>>(
      `/screening/profiles/${encodeURIComponent(profileId)}/duplicate`,
      body,
    );
    return response.data;
  },

  deleteProfile: async (profileId: string): Promise<void> => {
    await apiClient.delete<undefined>(`/screening/profiles/${encodeURIComponent(profileId)}`);
  },

  run: async (body: RunScreeningRequest): Promise<ScreeningRunEnvelope> => {
    const response = await apiClient.post<SuccessResponse<ScreeningRunEnvelope>>("/screening/run", body);
    return response.data;
  },

  getResult: async (resultId: string): Promise<ScreeningRunEnvelope> => {
    const response = await apiClient.get<SuccessResponse<ScreeningRunEnvelope>>(
      `/screening/results/${encodeURIComponent(resultId)}`,
    );
    return response.data;
  },
};
