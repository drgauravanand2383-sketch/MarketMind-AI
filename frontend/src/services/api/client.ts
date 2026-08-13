import type { ApiErrorCode, ErrorResponse, ValidationErrorResponse } from "@/types/api";
import { ApiError } from "@/services/api/errors";
import { API_BASE_URL } from "@/services/api/config";

export type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE" | "PUT";

export interface RequestContext {
  url: string;
  init: RequestInit;
}

export type RequestInterceptor = (context: RequestContext) => RequestContext | Promise<RequestContext>;
export type ResponseInterceptor = (response: Response, context: RequestContext) => Response | Promise<Response>;

export interface RequestOptions {
  method?: HttpMethod;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Skip attaching an Authorization header — used by login/refresh
   * themselves, which must never send a (possibly stale) token. */
  skipAuth?: boolean;
  /** Skip the retry policy for this one call — used for non-idempotent
   * calls a caller wants to control retrying themselves. */
  skipRetry?: boolean;
}

export interface RetryPolicy {
  maxRetries: number;
  baseDelayMs: number;
  retryableStatusCodes: number[];
}

export interface AuthHooks {
  getAccessToken: () => string | null;
  /** Attempt a token refresh; return the new access token, or `null` if
   * refresh failed (the client then surfaces the original 401 as-is). */
  onUnauthorized: () => Promise<string | null>;
}

const DEFAULT_RETRY_POLICY: RetryPolicy = {
  maxRetries: 2,
  baseDelayMs: 300,
  retryableStatusCodes: [502, 503, 504],
};

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    "message" in value &&
    typeof (value as { error: unknown }).error === "string"
  );
}

function isValidationErrorResponse(value: unknown): value is ValidationErrorResponse {
  return isErrorResponse(value) && "details" in value && Array.isArray((value as { details: unknown }).details);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * A typed fetch wrapper for the frozen `/api/v1` contract
 * (`docs/release/API_CONTRACT_V1.md`). Owns exactly the cross-cutting
 * HTTP concerns — auth header attachment, 401-triggered token refresh,
 * retry-with-backoff, and error normalization — never any domain logic;
 * each feature's own `services/api/*` module supplies the path and the
 * response type.
 */
export class ApiClient {
  private readonly baseUrl: string;
  private readonly retryPolicy: RetryPolicy;
  private authHooks: AuthHooks | null = null;
  private readonly requestInterceptors: RequestInterceptor[] = [];
  private readonly responseInterceptors: ResponseInterceptor[] = [];
  private refreshInFlight: Promise<string | null> | null = null;

  constructor(baseUrl: string, retryPolicy: Partial<RetryPolicy> = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.retryPolicy = { ...DEFAULT_RETRY_POLICY, ...retryPolicy };
  }

  /** Wired once at app startup (`src/app/providers.tsx`) — kept out of
   * the constructor so this module never imports the auth store
   * directly (no circular import between the client and the store that
   * uses it). */
  setAuthHooks(hooks: AuthHooks): void {
    this.authHooks = hooks;
  }

  addRequestInterceptor(interceptor: RequestInterceptor): void {
    this.requestInterceptors.push(interceptor);
  }

  addResponseInterceptor(interceptor: ResponseInterceptor): void {
    this.responseInterceptors.push(interceptor);
  }

  async get<T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  async post<T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  async patch<T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "PATCH", body });
  }

  async delete<T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = options.method ?? "GET";
    let networkAttempt = 0;
    let hasRetriedAfterRefresh = false;

    for (;;) {
      let context = this.buildContext(path, method, options);
      for (const interceptor of this.requestInterceptors) {
        context = await interceptor(context);
      }

      let response: Response;
      try {
        response = await fetch(context.url, context.init);
      } catch (cause) {
        if (!options.skipRetry && networkAttempt < this.retryPolicy.maxRetries) {
          await sleep(this.retryPolicy.baseDelayMs * 2 ** networkAttempt);
          networkAttempt += 1;
          continue;
        }
        throw new ApiError({
          message: cause instanceof Error ? cause.message : "Network request failed.",
          status: 0,
          code: "network_error",
        });
      }

      for (const interceptor of this.responseInterceptors) {
        response = await interceptor(response, context);
      }

      // A 401 gets exactly one refresh-and-retry attempt per call — never
      // an unbounded loop, even if the newly refreshed token is somehow
      // rejected again.
      if (response.status === 401 && !options.skipAuth && this.authHooks && !hasRetriedAfterRefresh) {
        hasRetriedAfterRefresh = true;
        const refreshedToken = await this.refreshAccessToken();
        if (refreshedToken) {
          continue;
        }
      }

      if (
        !options.skipRetry &&
        this.retryPolicy.retryableStatusCodes.includes(response.status) &&
        networkAttempt < this.retryPolicy.maxRetries
      ) {
        await sleep(this.retryPolicy.baseDelayMs * 2 ** networkAttempt);
        networkAttempt += 1;
        continue;
      }

      return this.parseResponse<T>(response);
    }
  }

  private async refreshAccessToken(): Promise<string | null> {
    if (!this.authHooks) return null;
    // Coalesce concurrent 401s into one refresh call, not one per request.
    this.refreshInFlight ??= this.authHooks.onUnauthorized().finally(() => {
      this.refreshInFlight = null;
    });
    return this.refreshInFlight;
  }

  private buildContext(path: string, method: HttpMethod, options: RequestOptions): RequestContext {
    const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    if (!options.skipAuth) {
      const token = this.authHooks?.getAccessToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
    }
    return {
      url: `${this.baseUrl}${path}`,
      init: {
        method,
        headers,
        ...(options.body !== undefined && { body: JSON.stringify(options.body) }),
        ...(options.signal !== undefined && { signal: options.signal }),
      },
    };
  }

  private async parseResponse<T>(response: Response): Promise<T> {
    const text = await response.text();
    const parsed: unknown = text.length > 0 ? safeJsonParse(text) : undefined;

    if (response.ok) {
      return parsed as T;
    }

    if (isValidationErrorResponse(parsed)) {
      throw new ApiError({
        message: parsed.message,
        status: response.status,
        code: parsed.error as ApiErrorCode,
        details: parsed.details,
      });
    }
    if (isErrorResponse(parsed)) {
      throw new ApiError({ message: parsed.message, status: response.status, code: parsed.error as ApiErrorCode });
    }
    throw new ApiError({
      message: `Request failed with status ${String(response.status)}.`,
      status: response.status,
      code: "parse_error",
    });
  }
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

export const apiClient = new ApiClient(API_BASE_URL);
