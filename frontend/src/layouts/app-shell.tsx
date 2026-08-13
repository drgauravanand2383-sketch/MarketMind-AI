import { useEffect, type ReactNode } from "react";
import { Outlet } from "@tanstack/react-router";
import { ConnectivityBanner } from "@/components/connectivity-banner";
import { ErrorBoundary } from "@/components/error-boundary";
import { LoadingBoundary } from "@/components/loading-boundary";
import { ShortcutsHelpDialog } from "@/components/shortcuts-help-dialog";
import { ErrorState } from "@/components/states/error-state";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";
import { useRealtimeSync } from "@/hooks/use-realtime-sync";
import { useSessionExpiryRedirect } from "@/hooks/use-session-expiry-redirect";
import { Breadcrumbs } from "@/layouts/breadcrumbs";
import { Sidebar } from "@/layouts/sidebar";
import { TopNav } from "@/layouts/top-nav";
import { Footer } from "@/layouts/footer";
import { markAppShellMounted } from "@/lib/performance-timing";

/** The authenticated application shell: sidebar + top nav + breadcrumbs
 * + footer around a routed `<Outlet />`. Public routes (login) render
 * outside this tree entirely — see `src/pages/__root.tsx` — since they
 * need none of this chrome. `useRealtimeSync()` is mounted here and only
 * here — it owns the app's one `useWebSocket()` call for the lifetime of
 * the authenticated session (this component is itself gated by
 * `_authenticated.tsx`'s `beforeLoad`, so mount/unmount already tracks
 * login/logout for free). `useSessionExpiryRedirect()` is mounted here
 * too, so a mid-session refresh failure redirects immediately rather
 * than waiting for the next navigation. `useKeyboardShortcuts()` is the
 * one global keydown listener behind Milestone 9's keyboard shortcuts;
 * `ShortcutsHelpDialog` renders the "?" cheatsheet it can open. */
export function AppShell(): ReactNode {
  useRealtimeSync();
  useSessionExpiryRedirect();
  useKeyboardShortcuts();

  useEffect(() => {
    markAppShellMounted();
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <TopNav />
      <ConnectivityBanner />
      <ShortcutsHelpDialog />
      <div className="flex flex-1">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Breadcrumbs />
          <main className="min-w-0 flex-1">
            <ErrorBoundary
              fallback={(error, reset) => (
                <div className="p-6">
                  <ErrorState message={error.message} onRetry={reset} />
                </div>
              )}
            >
              <LoadingBoundary>
                <Outlet />
              </LoadingBoundary>
            </ErrorBoundary>
          </main>
        </div>
      </div>
      <Footer />
    </div>
  );
}
