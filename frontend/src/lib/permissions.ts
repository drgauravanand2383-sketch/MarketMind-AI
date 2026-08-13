import { redirect } from "@tanstack/react-router";
import { useAuthStore } from "@/store/auth-store";

/** Checks the current user's permission list — the same strings the
 * backend's own `RequirePermission` policy checks
 * (`app.auth.policies`), just evaluated client-side for UI gating. This
 * is a UX convenience only, never a security boundary: the backend
 * enforces every permission itself, on every request, regardless of
 * what the frontend does or doesn't render. */
export function hasPermission(permission: string): boolean {
  return useAuthStore.getState().user?.permissions.includes(permission) ?? false;
}

/** Reactive form of `hasPermission`, for components (the sidebar,
 * dashboard quick-nav cards) that need to re-render if the signed-in
 * user's permission list ever changes — `hasPermission` itself is a
 * one-shot read, correct for a `beforeLoad` guard but not for a render. */
export function useHasPermission(permission: string): boolean {
  return useAuthStore((state) => state.user?.permissions.includes(permission) ?? false);
}

/** A route `beforeLoad` guard factory: redirects to `/forbidden` if the
 * authenticated user lacks `permission`. Assumes it runs after
 * `_authenticated`'s own "are you logged in at all" guard (nested routes
 * run their parent's `beforeLoad` first) — it only ever has to
 * distinguish "authenticated but lacking this permission" from "has it". */
export function requirePermission(permission: string) {
  return () => {
    if (!hasPermission(permission)) {
      throw redirect({ to: "/forbidden" });
    }
  };
}
