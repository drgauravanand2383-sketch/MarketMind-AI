import type { ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { SkeletonList } from "@/components/states/skeleton";
import { useSignalDefinitionsList } from "@/hooks/use-signals";

export function SignalDefinitionPicker({
  selectedDefinitionId,
  onSelect,
}: {
  selectedDefinitionId: string;
  onSelect: (definitionId: string) => void;
}): ReactNode {
  const definitions = useSignalDefinitionsList({ page: 1, page_size: 100, sort: "name", direction: "asc" });

  if (definitions.isPending) return <SkeletonList rows={2} rowClassName="h-8 w-full" />;

  if (definitions.isSuccess && definitions.data.data.length === 0) {
    return <EmptyState title="No signal definitions" description="No signal definitions exist to evaluate against yet." />;
  }

  return (
    <div>
      <label htmlFor="signal-definition" className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
        Signal definition
      </label>
      <select
        id="signal-definition"
        value={selectedDefinitionId}
        onChange={(event) => {
          onSelect(event.target.value);
        }}
        className="w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        <option value="">Select a definition…</option>
        {definitions.data?.data.map((definition) => (
          <option key={definition.id} value={definition.id}>
            {definition.name} ({definition.category})
          </option>
        ))}
      </select>
    </div>
  );
}
