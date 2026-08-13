import { apiClient } from "@/services/api/client";
import type { SuccessResponse } from "@/types/api";
import type { BacktestResult, BacktestRun, CreateBacktestRequest } from "@/types/backtesting";

/** Thin wrappers over `/api/v1/backtests/*`. `run_id` is the
 * `BacktestRequest.id` throughout — there is no separate run/result id. */
export const backtestingApi = {
  /** Creates the backtest request and runs it synchronously in one call
   * — the full aggregate `BacktestResult` comes back directly, not a
   * pending/polling handle. */
  create: async (body: CreateBacktestRequest): Promise<BacktestResult> => {
    const response = await apiClient.post<SuccessResponse<BacktestResult>>("/backtests", body);
    return response.data;
  },

  getRun: async (runId: string): Promise<BacktestRun> => {
    const response = await apiClient.get<SuccessResponse<BacktestRun>>(`/backtests/${encodeURIComponent(runId)}`);
    return response.data;
  },

  getResults: async (runId: string): Promise<BacktestResult> => {
    const response = await apiClient.get<SuccessResponse<BacktestResult>>(
      `/backtests/${encodeURIComponent(runId)}/results`,
    );
    return response.data;
  },
};
