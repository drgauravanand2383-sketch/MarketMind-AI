import type { ReactElement, ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook } from "@testing-library/react";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function queryClientWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }): ReactNode {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

export function renderWithQueryClient(ui: ReactElement, queryClient: QueryClient = createTestQueryClient()): ReturnType<typeof render> {
  return render(ui, { wrapper: queryClientWrapper(queryClient) });
}

/** For testing hooks (mutations especially) directly, without mounting a
 * full component tree — returns both the render result and the
 * `QueryClient` so a test can inspect/seed the cache directly. */
export function renderHookWithQueryClient<TResult, TProps>(
  hook: (props: TProps) => TResult,
  queryClient: QueryClient = createTestQueryClient(),
): ReturnType<typeof renderHook<TResult, TProps>> & { queryClient: QueryClient } {
  return { ...renderHook(hook, { wrapper: queryClientWrapper(queryClient) }), queryClient };
}
