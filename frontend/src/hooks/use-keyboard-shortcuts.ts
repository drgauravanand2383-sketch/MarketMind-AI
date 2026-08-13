import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuthStore } from "@/store/auth-store";
import { useShortcutsStore, type ShortcutAction } from "@/store/shortcuts-store";

// A stable, module-level reference — see `sidebar.tsx`'s identical
// `NO_PERMISSIONS` for why a fresh `[]` fallback in the selector itself
// would trip React's `useSyncExternalStore` infinite-loop detector.
const NO_PERMISSIONS: string[] = [];

const PERMISSION_FOR_ACTION: Partial<Record<ShortcutAction, string>> = {
  goToWatchlists: "watchlist:read",
  goToDecisionCenter: "portfolio:read",
  goToHistoricalAnalysis: "backtest:read",
};

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

function actionForKey(bindings: Record<ShortcutAction, string>, key: string): ShortcutAction | null {
  const entry = (Object.entries(bindings) as [ShortcutAction, string][]).find(([, boundKey]) => boundKey === key);
  return entry ? entry[0] : null;
}

/**
 * The single global keydown listener behind Milestone 9's "Keyboard
 * Productivity" shortcuts — mounted once in `AppShell`, alongside
 * `useRealtimeSync`/`useSessionExpiryRedirect`. Shortcuts never fire
 * while focus is inside a text field (`isEditableTarget`) or a modifier
 * key is held, so they never hijack normal typing. Navigation targets
 * gated by a real backend permission (Watchlists/Decision Center/
 * Historical Analysis) are silently no-ops for a user who can't see
 * that domain — mirrors `sidebar.tsx`'s own `useVisibleFeatureItems`
 * gating, so a shortcut never navigates someone into an immediate
 * `/forbidden` redirect.
 */
export function useKeyboardShortcuts(): void {
  const navigate = useNavigate();
  const bindings = useShortcutsStore((state) => state.bindings);
  const openHelp = useShortcutsStore((state) => state.openHelp);
  const permissions = useAuthStore((state) => state.user?.permissions ?? NO_PERMISSIONS);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isEditableTarget(event.target)) return;

      const action = actionForKey(bindings, event.key);
      if (!action) return;

      if (action === "search") {
        const searchInput = document.querySelector<HTMLElement>('[data-shortcut-target="search"]');
        if (!searchInput) return;
        event.preventDefault();
        searchInput.focus();
        return;
      }

      if (action === "help") {
        event.preventDefault();
        openHelp();
        return;
      }

      const requiredPermission = PERMISSION_FOR_ACTION[action];
      if (requiredPermission && !permissions.includes(requiredPermission)) return;

      event.preventDefault();
      switch (action) {
        case "goToDashboard":
          void navigate({ to: "/" });
          break;
        case "goToWatchlists":
          void navigate({ to: "/watchlists" });
          break;
        case "goToDecisionCenter":
          void navigate({ to: "/decisions" });
          break;
        case "goToHistoricalAnalysis":
          void navigate({ to: "/historical-analysis" });
          break;
        case "goToNotifications":
          void navigate({ to: "/notifications" });
          break;
        case "goToSettings":
          void navigate({ to: "/settings" });
          break;
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [bindings, navigate, openHelp, permissions]);
}
