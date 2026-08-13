import type { ReactNode } from "react";
import { createRootRoute, Outlet } from "@tanstack/react-router";
import { Spinner } from "@/components/loading-boundary";
import { StatusPage } from "@/components/states/status-page";
import { resolveSession } from "@/store/auth-store";

function RootError({ error }: { error: Error }): ReactNode {
  return (
    <StatusPage
      code="Error"
      title="Something went wrong"
      description={error.message}
      action={{ label: "Back to dashboard", to: "/" }}
    />
  );
}

function SessionLoading(): ReactNode {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Spinner label="Loading your session…" />
    </div>
  );
}

export const Route = createRootRoute({
  // Runs once, before any child route's own `beforeLoad` — resolving the
  // persisted session here (rather than in a component effect) means
  // every route guard downstream sees a settled `status`, never "idle".
  beforeLoad: async () => {
    await resolveSession();
  },
  // Only shown if `beforeLoad` takes longer than `pendingMs` (TanStack
  // Router's default 1s) — resolving a persisted session is normally
  // instant; this only appears on a slow first refresh-on-load network
  // round trip.
  pendingComponent: SessionLoading,
  component: () => <Outlet />,
  notFoundComponent: () => (
    <StatusPage code="404" title="Page not found" description="This page doesn't exist." action={{ label: "Back to dashboard", to: "/" }} />
  ),
  errorComponent: ({ error }) => <RootError error={error} />,
});
