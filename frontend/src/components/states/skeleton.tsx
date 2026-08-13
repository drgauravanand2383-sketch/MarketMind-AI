import type { ReactNode } from "react";

/** One pulsing placeholder block — compose via `className` for whatever
 * shape a loading panel needs (a line, an avatar, a card). Kept to a
 * single primitive rather than one variant per shape, since Tailwind
 * utility classes already express the shape at the call site. */
export function Skeleton({ className = "h-4 w-full" }: { className?: string }): ReactNode {
  return <div aria-hidden="true" className={`animate-pulse rounded-md bg-slate-200 dark:bg-slate-800 ${className}`} />;
}

export function SkeletonList({ rows = 3, rowClassName = "h-10 w-full" }: { rows?: number; rowClassName?: string }): ReactNode {
  return (
    <div role="status" aria-label="Loading" className="flex flex-col gap-2">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className={rowClassName} />
      ))}
    </div>
  );
}
