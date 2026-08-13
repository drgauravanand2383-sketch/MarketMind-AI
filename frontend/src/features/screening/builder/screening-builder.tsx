import { useState, type ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { LoadingButton } from "@/components/forms/loading-button";
import { FilterRow } from "@/features/screening/builder/filter-row";
import { generateFilterId, generateGroupId } from "@/features/screening/builder/group-utils";
import { GroupList } from "@/features/screening/builder/group-list";
import { validateDraft } from "@/features/screening/builder/validate-draft";
import { SCREENABLE_FIELDS } from "@/features/screening/screenable-fields";
import type { LogicalGroup, ScreenFilter } from "@/types/screening";

export interface ScreeningBuilderProps {
  filters: ScreenFilter[];
  groups: LogicalGroup[];
  isSaving: boolean;
  onSave: (filters: ScreenFilter[], groups: LogicalGroup[]) => void;
}

function reorder<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  const [moved] = next.splice(index, 1);
  if (moved === undefined) return items;
  next.splice(target, 0, moved);
  return next;
}

/** Filters/groups edited as local draft state, only sent to the backend
 * (via the caller's `onSave`, wired to `useUpdateScreeningProfile`'s
 * optimistic `PATCH`) once the user explicitly saves — never
 * auto-persisted per keystroke. */
export function ScreeningBuilder({ filters, groups, isSaving, onSave }: ScreeningBuilderProps): ReactNode {
  const [draftFilters, setDraftFilters] = useState(filters);
  const [draftGroups, setDraftGroups] = useState(groups);

  const errors = validateDraft(draftFilters, draftGroups);
  const firstField = SCREENABLE_FIELDS[0];

  function addFilter(): void {
    if (!firstField) return;
    setDraftFilters((prev) => [
      ...prev,
      { id: generateFilterId(), field: firstField.field, operator: "GREATER_THAN", value: null, group: null, enabled: true },
    ]);
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Filters</h3>
        {draftFilters.length === 0 ? (
          <EmptyState icon="🧮" title="No filters yet" description="Add a filter to start defining this screen's criteria." />
        ) : (
          <ul className="flex flex-col gap-2">
            {draftFilters.map((filter, index) => (
              <FilterRow
                key={filter.id}
                filter={filter}
                index={index}
                groups={draftGroups}
                canMoveUp={index > 0}
                canMoveDown={index < draftFilters.length - 1}
                onChange={(updated) => {
                  setDraftFilters((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
                }}
                onRemove={() => {
                  setDraftFilters((prev) => prev.filter((f) => f.id !== filter.id));
                }}
                onMoveUp={() => {
                  setDraftFilters((prev) => reorder(prev, index, -1));
                }}
                onMoveDown={() => {
                  setDraftFilters((prev) => reorder(prev, index, 1));
                }}
              />
            ))}
          </ul>
        )}
        <button
          type="button"
          onClick={addFilter}
          className="mt-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Add filter
        </button>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Logical groups</h3>
        <GroupList
          groups={draftGroups}
          onChange={(updated) => {
            setDraftGroups((prev) => prev.map((g) => (g.id === updated.id ? updated : g)));
          }}
          onRemove={(groupId) => {
            setDraftGroups((prev) => prev.filter((g) => g.id !== groupId));
            setDraftFilters((prev) => prev.map((f) => (f.group === groupId ? { ...f, group: null } : f)));
            setDraftGroups((prev) => prev.map((g) => (g.parent_group === groupId ? { ...g, parent_group: null } : g)));
          }}
          onAdd={() => {
            setDraftGroups((prev) => [...prev, { id: generateGroupId(), logic: "AND", parent_group: null }]);
          }}
        />
      </div>

      {errors.length > 0 && (
        <ul role="alert" className="flex flex-col gap-1 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {errors.map((error, index) => (
            <li key={index}>{error}</li>
          ))}
        </ul>
      )}

      <div>
        <LoadingButton
          type="button"
          isLoading={isSaving}
          loadingText="Saving…"
          disabled={errors.length > 0}
          onClick={() => {
            onSave(draftFilters, draftGroups);
          }}
        >
          Save changes
        </LoadingButton>
      </div>
    </div>
  );
}
