import type { ReactNode } from "react";
import { wouldCreateCycle } from "@/features/screening/builder/group-utils";
import type { LogicalGroup } from "@/types/screening";

const SELECT_CLASS =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

export interface GroupListProps {
  groups: LogicalGroup[];
  onChange: (updated: LogicalGroup) => void;
  onRemove: (groupId: string) => void;
  onAdd: () => void;
}

/** Logical groups combine their direct children (filters/sub-groups) with
 * AND or OR — a filter or group with `group`/`parent_group: null` is a
 * direct child of the profile's own implicit (always-AND) root. Parent
 * choices that would create a cycle are excluded from the dropdown
 * entirely, mirroring the backend's own rejection of one. */
export function GroupList({ groups, onChange, onRemove, onAdd }: GroupListProps): ReactNode {
  return (
    <div className="flex flex-col gap-2">
      {groups.length === 0 && <p className="text-sm text-slate-500 dark:text-slate-400">No logical groups — every filter is ANDed together.</p>}
      <ul className="flex flex-col gap-2">
        {groups.map((group) => {
          const availableParents = groups.filter((candidate) => !wouldCreateCycle(groups, group.id, candidate.id));
          return (
            <li key={group.id} className="flex flex-wrap items-center gap-2 rounded-md border border-slate-200 p-2 text-sm dark:border-slate-800">
              <span className="font-mono text-xs text-slate-500 dark:text-slate-400">{group.id}</span>

              <label className="sr-only" htmlFor={`${group.id}-logic`}>
                Logic
              </label>
              <select
                id={`${group.id}-logic`}
                value={group.logic}
                onChange={(event) => {
                  onChange({ ...group, logic: event.target.value as "AND" | "OR" });
                }}
                className={SELECT_CLASS}
              >
                <option value="AND">AND</option>
                <option value="OR">OR</option>
              </select>

              <label className="sr-only" htmlFor={`${group.id}-parent`}>
                Parent group
              </label>
              <select
                id={`${group.id}-parent`}
                value={group.parent_group ?? ""}
                onChange={(event) => {
                  onChange({ ...group, parent_group: event.target.value === "" ? null : event.target.value });
                }}
                className={SELECT_CLASS}
              >
                <option value="">Top-level (root)</option>
                {availableParents.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.id}
                  </option>
                ))}
              </select>

              <button
                type="button"
                onClick={() => {
                  onRemove(group.id);
                }}
                className="ml-auto rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
              >
                Remove
              </button>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        onClick={onAdd}
        className="self-start rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        Add group
      </button>
    </div>
  );
}
