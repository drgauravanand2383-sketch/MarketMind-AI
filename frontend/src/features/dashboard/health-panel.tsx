import type { ReactNode } from "react";
import { SkeletonList } from "@/components/states/skeleton";
import { ErrorState } from "@/components/states/error-state";
import { useHealth } from "@/hooks/use-health";
import { StatusBadge } from "@/features/dashboard/status-badge";
import type { ComponentHealth } from "@/types/health";

function ComponentList({ title, components }: { title: string; components: ComponentHealth[] }): ReactNode {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{title}</h3>
      <ul className="mt-2 flex flex-col gap-2">
        {components.map((component) => (
          <li
            key={component.name}
            className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm dark:border-slate-800"
          >
            <div>
              <p className="font-medium text-slate-900 dark:text-slate-100">{component.name}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{component.message}</p>
            </div>
            <StatusBadge state={component.state} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HealthPanel(): ReactNode {
  const health = useHealth();

  if (health.isPending) {
    return <SkeletonList rows={4} rowClassName="h-14 w-full" />;
  }

  if (health.isError) {
    return (
      <ErrorState
        title="Couldn't load system health"
        message={health.error.message}
        onRetry={() => {
          void health.refetch();
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Overall</span>
        <StatusBadge state={health.data.state} />
        <span className="text-sm text-slate-500 dark:text-slate-400">{health.data.summary}</span>
      </div>
      <ComponentList title="Repositories" components={health.data.repositories} />
      <ComponentList title="Services" components={health.data.services} />
      <ComponentList title="Dependencies" components={health.data.dependencies} />
    </div>
  );
}
