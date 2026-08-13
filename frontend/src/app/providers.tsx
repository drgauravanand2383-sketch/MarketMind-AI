import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { queryClient } from "@/app/query-client";
import { PreferencesProvider } from "@/app/preferences-provider";
import { ThemeProvider } from "@/app/theme-provider";
import { NotificationCenter } from "@/components/notifications/notification-center";
import { apiClient } from "@/services/api/client";
import { getAccessTokenValue, useAuthStore } from "@/store/auth-store";

// Wired once, at module load, rather than inside a component effect —
// `ApiClient` needs these hooks available before the very first request
// a render might trigger, not after a first effect flush. Session
// resolution itself (deciding "idle" -> "authenticated"/"unauthenticated")
// lives in the root route's `beforeLoad` instead of here — see
// `src/pages/__root.tsx` — so every route guard sees a settled status
// with no separate effect racing the router's first render.
apiClient.setAuthHooks({
  getAccessToken: getAccessTokenValue,
  onUnauthorized: () => useAuthStore.getState().refresh(),
});

export function AppProviders({ children }: { children: ReactNode }): ReactNode {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <PreferencesProvider>
          {children}
          <NotificationCenter />
        </PreferencesProvider>
      </ThemeProvider>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
