import { useEffect } from "react";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useAuthStore } from "@/store/auth-store";

/**
 * Reacts to `auth-store.ts`'s `sessionExpired` flag the moment it flips
 * true (a refresh failure mid-session), instead of waiting for the next
 * route navigation to trigger `_authenticated.tsx`'s `beforeLoad` guard
 * — a Milestone 9 audit finding: previously a user mid-task got no
 * feedback until they happened to navigate somewhere. `beforeLoad`'s own
 * `sessionExpired` check stays in place as a fallback for the case where
 * the flag is already set before `AppShell` (and this hook) ever mounts
 * — e.g. a hard page load whose initial `resolveSession()` refresh
 * fails before routing occurs.
 */
export function useSessionExpiryRedirect(): void {
  const sessionExpired = useAuthStore((state) => state.sessionExpired);
  const navigate = useNavigate();
  const currentHref = useRouterState({ select: (state) => state.location.href });

  useEffect(() => {
    if (!sessionExpired) return;
    useAuthStore.setState({ sessionExpired: false });
    void navigate({ to: "/unauthorized", search: { redirect: currentHref } });
  }, [sessionExpired, navigate, currentHref]);
}
