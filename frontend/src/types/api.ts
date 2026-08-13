/**
 * Shared response envelope shapes — mirrors `app.api.v1.schemas.common`
 * on the backend exactly (Sprint 55, frozen as of RC1). Every `/api/v1`
 * response is one of these three shapes; nothing else.
 */

export interface MetadataResponse {
  request_id: string;
  timestamp: string;
  api_version: string;
}

export interface SuccessResponse<TData> {
  data: TData;
  meta: MetadataResponse;
}

export interface PaginatedResponse<TItem> {
  data: TItem[];
  total: number;
  page: number;
  page_size: number;
  meta: MetadataResponse;
}

export interface ErrorResponse {
  error: string;
  message: string;
  meta: MetadataResponse;
}

export interface ValidationErrorDetail {
  location: string[];
  message: string;
  type: string;
}

export interface ValidationErrorResponse extends ErrorResponse {
  details: ValidationErrorDetail[];
}

/** The closed set of `error` codes the backend ever returns — see
 * `docs/release/API_CONTRACT_V1.md` §5. */
export type ApiErrorCode =
  | "not_found"
  | "method_not_allowed"
  | "service_unavailable"
  | "conflict"
  | "domain_error"
  | "validation_error"
  | "http_error"
  | "internal_error";
