import { createFileRoute, redirect } from "@tanstack/react-router";
import { AppShell } from "@/layouts/app-shell";
import { useAuthStore } from "@/store/auth-store";

export const Route = createFileRoute("/_authenticated")({
  beforeLoad: ({ location }) => {
    const { status, sessionExpired } = useAuthStore.getState();
    if (status === "authenticated") return;

    // A session that expired mid-use (refresh failed) gets an
    // explanatory interstitial (`/unauthorized`); never having signed in
    // (or a deliberate logout) goes straight to the plain login form —
    // see `sessionExpired`'s docstring in `src/store/auth-store.ts`.
    if (sessionExpired) {
      useAuthStore.setState({ sessionExpired: false });
      throw redirect({ to: "/unauthorized", search: { redirect: location.href } });
    }
    throw redirect({ to: "/login", search: { redirect: location.href } });
  },
  component: AppShell,
});
