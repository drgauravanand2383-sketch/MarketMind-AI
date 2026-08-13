import { lazy, Suspense, type ReactNode } from "react";
import { Skeleton } from "@/components/states/skeleton";

// Lazy-loaded: these 3 charts are the only reason the ~107kB-gzip Recharts
// bundle used to load on every dashboard visit (the default post-login
// landing page), even for users who never scroll to a chart card or who
// have hidden/reordered it out of view (Milestone 9 audit finding).
// `React.lazy` defers the `import()` until first render, and each lazy
// wrapper is created once at module scope (not per-render). Kept in their
// own component-only file (rather than inline in `dashboard-card-registry
// .ts`, which also exports the non-component `DASHBOARD_CARDS`/
// `getDashboardCard`) so `react-refresh/only-export-components` stays
// satisfied.
const LazyApiLatencyChart = lazy(() =>
  import("@/features/dashboard/charts/api-latency-chart").then((m) => ({ default: m.ApiLatencyChart })),
);
const LazyHealthSummaryChart = lazy(() =>
  import("@/features/dashboard/charts/health-summary-chart").then((m) => ({ default: m.HealthSummaryChart })),
);
const LazyServiceAvailabilityChart = lazy(() =>
  import("@/features/dashboard/charts/service-availability-chart").then((m) => ({ default: m.ServiceAvailabilityChart })),
);

function ChartFallback(): ReactNode {
  return <Skeleton className="h-56 w-full" />;
}

export function ApiLatencyChart(): ReactNode {
  return (
    <Suspense fallback={<ChartFallback />}>
      <LazyApiLatencyChart />
    </Suspense>
  );
}

export function HealthSummaryChart(): ReactNode {
  return (
    <Suspense fallback={<ChartFallback />}>
      <LazyHealthSummaryChart />
    </Suspense>
  );
}

export function ServiceAvailabilityChart(): ReactNode {
  return (
    <Suspense fallback={<ChartFallback />}>
      <LazyServiceAvailabilityChart />
    </Suspense>
  );
}
