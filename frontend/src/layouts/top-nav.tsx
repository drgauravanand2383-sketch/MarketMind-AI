import type { ReactNode } from "react";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/layouts/user-menu";
import { useUiStore } from "@/store/ui-store";

export function TopNav(): ReactNode {
  const setMobileNavOpen = useUiStore((state) => state.setMobileNavOpen);

  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800 sm:px-4">
      <div className="flex items-center gap-2 sm:gap-3">
        <button
          type="button"
          onClick={() => {
            setMobileNavOpen(true);
          }}
          aria-label="Open navigation"
          className="rounded-md p-2 text-slate-600 hover:bg-slate-100 sm:hidden dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <span aria-hidden="true">☰</span>
        </button>
        <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">MarketMind AI</span>
      </div>
      <div className="flex items-center gap-2 sm:gap-3">
        <NotificationBell />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
