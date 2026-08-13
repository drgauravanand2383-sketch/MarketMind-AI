import { apiClient } from "@/services/api/client";
import type { SuccessResponse } from "@/types/api";
import type { AuthenticationResponse, LoginRequest, LogoutRequest, RefreshTokenRequest } from "@/types/auth";

/** Thin wrappers over `POST /api/v1/auth/*` — no logic beyond the HTTP
 * call itself; token persistence/state lives in `src/store/auth-store.ts`. */
export const authApi = {
  login: async (body: LoginRequest): Promise<AuthenticationResponse> => {
    const response = await apiClient.post<SuccessResponse<AuthenticationResponse>>("/auth/login", body, {
      skipAuth: true,
    });
    return response.data;
  },

  refresh: async (body: RefreshTokenRequest): Promise<AuthenticationResponse> => {
    const response = await apiClient.post<SuccessResponse<AuthenticationResponse>>("/auth/refresh", body, {
      skipAuth: true,
    });
    return response.data;
  },

  logout: async (body: LogoutRequest): Promise<void> => {
    await apiClient.post<undefined>("/auth/logout", body);
  },
};
