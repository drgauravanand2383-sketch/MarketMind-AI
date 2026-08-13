import { Suspense, type ReactNode } from "react";

export function Spinner({ label = "Loading…" }: { label?: string }): ReactNode {
  return (
    <div role="status" className="flex items-center justify-center gap-3 p-8 text-slate-500 dark:text-slate-400">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function LoadingBoundary({ children, fallback }: { children: ReactNode; fallback?: ReactNode }): ReactNode {
  return <Suspense fallback={fallback ?? <Spinner />}>{children}</Suspense>;
}
