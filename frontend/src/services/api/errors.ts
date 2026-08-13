import type { ApiErrorCode, ValidationErrorDetail } from "@/types/api";

/**
 * Thrown by `ApiClient` for every non-2xx response and every network
 * failure. Carries the parsed backend error shape when one was
 * available (`docs/release/API_CONTRACT_V1.md` §5), or a synthetic
 * `network_error`/`parse_error` code when the response never arrived or
 * never parsed — callers can rely on `status`/`code` always being
 * present either way.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | "network_error" | "parse_error";
  readonly details: ValidationErrorDetail[] | undefined;

  constructor(params: {
    message: string;
    status: number;
    code: ApiErrorCode | "network_error" | "parse_error";
    details?: ValidationErrorDetail[];
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.details = params.details;
  }

  get isNetworkError(): boolean {
    return this.code === "network_error";
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
}
