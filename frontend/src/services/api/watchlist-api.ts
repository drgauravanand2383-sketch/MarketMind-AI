import { apiClient } from "@/services/api/client";
import { buildQueryString } from "@/lib/query-string";
import type { PaginatedResponse, SuccessResponse } from "@/types/api";
import type {
  AddCompanyRequest,
  CreateWatchlistRequest,
  RenameWatchlistRequest,
  UpdateNotesRequest,
  Watchlist,
  WatchlistListParams,
  WatchlistSnapshot,
} from "@/types/watchlist";

/** Thin wrappers over `/api/v1/watchlists/*` — no logic beyond the HTTP
 * call and unwrapping `.data`; filtering/sorting/pagination are all
 * server-side (the backend's own query params), never recomputed here. */
export const watchlistApi = {
  list: async (params: WatchlistListParams = {}): Promise<PaginatedResponse<Watchlist>> => {
    return apiClient.get<PaginatedResponse<Watchlist>>(`/watchlists${buildQueryString(params)}`);
  },

  get: async (watchlistId: string): Promise<Watchlist> => {
    const response = await apiClient.get<SuccessResponse<Watchlist>>(`/watchlists/${watchlistId}`);
    return response.data;
  },

  create: async (body: CreateWatchlistRequest): Promise<Watchlist> => {
    const response = await apiClient.post<SuccessResponse<Watchlist>>("/watchlists", body);
    return response.data;
  },

  rename: async (watchlistId: string, body: RenameWatchlistRequest): Promise<Watchlist> => {
    const response = await apiClient.patch<SuccessResponse<Watchlist>>(`/watchlists/${watchlistId}`, body);
    return response.data;
  },

  /** `204 No Content` — deliberately typed `Promise<void>`, unlike every
   * other mutation here, which all return the updated `Watchlist`. */
  delete: async (watchlistId: string): Promise<void> => {
    await apiClient.delete<undefined>(`/watchlists/${watchlistId}`);
  },

  addCompany: async (watchlistId: string, body: AddCompanyRequest): Promise<Watchlist> => {
    const response = await apiClient.post<SuccessResponse<Watchlist>>(`/watchlists/${watchlistId}/companies`, body);
    return response.data;
  },

  /** `200` + the updated `Watchlist` — the one documented exception to
   * "DELETE returns 204" (`docs/release/API_CONTRACT_V1.md` §3):
   * removing one company still leaves a resource worth returning. */
  removeCompany: async (watchlistId: string, ticker: string): Promise<Watchlist> => {
    const response = await apiClient.delete<SuccessResponse<Watchlist>>(
      `/watchlists/${watchlistId}/companies/${encodeURIComponent(ticker)}`,
    );
    return response.data;
  },

  updateNotes: async (watchlistId: string, ticker: string, body: UpdateNotesRequest): Promise<Watchlist> => {
    const response = await apiClient.patch<SuccessResponse<Watchlist>>(
      `/watchlists/${watchlistId}/companies/${encodeURIComponent(ticker)}/notes`,
      body,
    );
    return response.data;
  },

  getSnapshot: async (watchlistId: string): Promise<WatchlistSnapshot> => {
    const response = await apiClient.get<SuccessResponse<WatchlistSnapshot>>(`/watchlists/${watchlistId}/snapshot`);
    return response.data;
  },
};
