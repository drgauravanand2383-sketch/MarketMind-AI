import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { EmptyState } from "@/components/states/empty-state";
import { FEATURE_NAV_ITEMS } from "@/lib/nav-items";
import { useAuthStore } from "@/store/auth-store";

export function QuickNavCards(): ReactNode {
  const permissions = useAuthStore((state) => state.user?.permissions ?? []);
  const visibleItems = FEATURE_NAV_ITEMS.filter((item) => permissions.includes(item.permission));

  if (visibleItems.length === 0) {
    return <EmptyState title="No workflows available" description="Your account doesn't have access to any investment workflows yet." />;
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {visibleItems.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          className="flex flex-col gap-2 rounded-lg border border-slate-200 p-4 transition-colors hover:border-brand-300 hover:bg-brand-50 dark:border-slate-800 dark:hover:border-brand-700 dark:hover:bg-brand-500/10"
        >
          <span aria-hidden="true" className="text-xl">
            {item.icon}
          </span>
          <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{item.label}</span>
          <span className="text-xs text-slate-500 dark:text-slate-400">{item.description}</span>
        </Link>
      ))}
    </div>
  );
}
