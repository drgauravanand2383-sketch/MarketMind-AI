import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Rectangle, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState } from "@/components/states/error-state";
import { Skeleton } from "@/components/states/skeleton";
import { useHealth } from "@/hooks/use-health";
import type { HealthState } from "@/types/health";

const AVAILABILITY_SCORE: Record<HealthState, number> = { HEALTHY: 100, DEGRADED: 50, UNHEALTHY: 0 };
const BAR_COLOR: Record<HealthState, string> = { HEALTHY: "#22c55e", DEGRADED: "#f59e0b", UNHEALTHY: "#ef4444" };
const FALLBACK_COLOR = "#94a3b8";

function isHealthState(value: unknown): value is HealthState {
  return value === "HEALTHY" || value === "DEGRADED" || value === "UNHEALTHY";
}

function extractState(payload: unknown): HealthState | undefined {
  if (payload && typeof payload === "object" && "state" in payload) {
    return isHealthState(payload.state) ? payload.state : undefined;
  }
  return undefined;
}

/** Per-service availability, scored from each service's real
 * `GET /health` state (`HEALTHY`/`DEGRADED`/`UNHEALTHY` -> 100/50/0) —
 * not a real uptime percentage the backend doesn't track, but a real
 * derivation of real data, not demo data. */
export function ServiceAvailabilityChart(): ReactNode {
  const health = useHealth();

  if (health.isPending) {
    return <Skeleton className="h-56 w-full" />;
  }
  if (health.isError) {
    return (
      <ErrorState
        title="Chart unavailable"
        message={health.error.message}
        onRetry={() => {
          void health.refetch();
        }}
      />
    );
  }
  if (health.data.services.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No services reported.</p>;
  }

  const data = health.data.services.map((service) => ({
    name: service.name,
    availability: AVAILABILITY_SCORE[service.state],
    state: service.state,
  }));

  return (
    <ResponsiveContainer width="100%" height={224}>
      <BarChart data={data} aria-label="Service availability">
        <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Bar
          dataKey="availability"
          radius={[4, 4, 0, 0]}
          shape={(props) => {
            const state = extractState(props.payload);
            const fill = state ? BAR_COLOR[state] : FALLBACK_COLOR;
            return <Rectangle x={props.x} y={props.y} width={props.width} height={props.height} radius={4} fill={fill} />;
          }}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
