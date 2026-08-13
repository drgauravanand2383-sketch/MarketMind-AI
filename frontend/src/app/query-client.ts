import { QueryCache, QueryClient, MutationCache } from "@tanstack/react-query";
import { ApiError } from "@/services/api/errors";
import { notify } from "@/store/notification-store";

/** `Query` and `Mutation`'s full generic signatures don't unify cleanly
 * (different default `TError`), and all this needs is `options.meta` —
 * so a minimal structural shape instead of importing either type. */
interface ErrorSourceWithMeta {
  options: { meta?: Record<string, unknown> };
}

/** Surfaces any `ApiError` a query/mutation surfaces as a toast — the
 * one global integration point for "API errors become notifications",
 * rather than every call site wiring this up itself. A `401` is
 * deliberately skipped: `ApiClient` already tried a silent
 * refresh-and-retry before a query ever sees it, and the resulting
 * session-expiry redirect (`src/store/auth-store.ts`'s `refresh()`
 * failure path) shows its own, more specific notification instead of a
 * generic one here. A mutation can also opt out entirely via
 * `meta: { suppressErrorToast: true }` — used by the optimistic
 * watchlist mutations (`src/hooks/use-watchlists.ts`), which already
 * show a more specific "...rolled back" toast themselves; without this,
 * a failed rename would show two toasts for one error. */
function notifyApiError(error: unknown, source: ErrorSourceWithMeta): void {
  if (!(error instanceof ApiError) || error.status === 401) return;
  if (source.options.meta?.suppressErrorToast === true) return;
  notify("error", error.message, { title: error.isForbidden ? "Access denied" : "Something went wrong" });
}

/** Default retry policy for server-state queries: never retry a 401/403
 * (retrying with the same stale token cannot succeed — `ApiClient`
 * already handles refresh-and-retry once, transparently, before a query
 * ever sees the failure) or a 404; retry everything else (network
 * blips, 5xx) up to twice. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403 || error.status === 404)) {
          return false;
        }
        return failureCount < 2;
      },
      staleTime: 30_000,
    },
    mutations: {
      retry: false,
    },
  },
  queryCache: new QueryCache({ onError: (error, query) => { notifyApiError(error, query); } }),
  mutationCache: new MutationCache({ onError: (error, _vars, _ctx, mutation) => { notifyApiError(error, mutation); } }),
});
