import type { ReactNode } from "react";
import { Legend, Pie, PieChart, ResponsiveContainer, Sector, Tooltip } from "recharts";
import { ErrorState } from "@/components/states/error-state";
import { Skeleton } from "@/components/states/skeleton";
import { useHealth } from "@/hooks/use-health";
import type { HealthState } from "@/types/health";

const COLORS: Record<HealthState, string> = {
  HEALTHY: "#22c55e",
  DEGRADED: "#f59e0b",
  UNHEALTHY: "#ef4444",
};
const FALLBACK_COLOR = "#94a3b8";

function isHealthState(value: unknown): value is HealthState {
  return value === "HEALTHY" || value === "DEGRADED" || value === "UNHEALTHY";
}

/** Component-state distribution across repositories/services/dependencies
 * — real data from `GET /health`, not mocked. */
export function HealthSummaryChart(): ReactNode {
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

  const allComponents = [...health.data.repositories, ...health.data.services, ...health.data.dependencies];
  const counts: Record<HealthState, number> = { HEALTHY: 0, DEGRADED: 0, UNHEALTHY: 0 };
  for (const component of allComponents) {
    counts[component.state] += 1;
  }
  const data = (Object.keys(counts) as HealthState[])
    .map((state) => ({ name: state, value: counts[state] }))
    .filter((entry) => entry.value > 0);

  if (data.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No components reported.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={224}>
      <PieChart aria-label="Component health summary">
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius={50}
          outerRadius={80}
          paddingAngle={2}
          shape={(props) => {
            const { cx, cy, innerRadius, outerRadius, startAngle, endAngle } = props;
            const fill = isHealthState(props.name) ? COLORS[props.name] : FALLBACK_COLOR;
            return (
              <Sector cx={cx} cy={cy} innerRadius={innerRadius} outerRadius={outerRadius} startAngle={startAngle} endAngle={endAngle} fill={fill} />
            );
          }}
        />
        <Tooltip />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
