import type { ReactNode } from "react";
import { SettingsField } from "@/features/settings/settings-field";
import { usePreferencesStore } from "@/store/preferences-store";
import { TABLE_PAGE_SIZE_OPTIONS } from "@/types/preferences";
import type { TablePageSize } from "@/types/preferences";

export function TablesTab(): ReactNode {
  const defaultPageSize = usePreferencesStore((state) => state.tables.defaultPageSize);
  const setDefaultPageSize = usePreferencesStore((state) => state.setDefaultPageSize);
  const resetSection = usePreferencesStore((state) => state.resetSection);

  return (
    <div className="flex flex-col">
      <SettingsField label="Default table page size" description="Applied to new watchlist, screening, and alert lists — you can still change it per list.">
        <label className="sr-only" htmlFor="default-page-size">
          Default table page size
        </label>
        <select
          id="default-page-size"
          value={defaultPageSize}
          onChange={(event) => {
            setDefaultPageSize(Number(event.target.value) as TablePageSize);
          }}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          {TABLE_PAGE_SIZE_OPTIONS.map((size) => (
            <option key={size} value={size}>
              {size} rows
            </option>
          ))}
        </select>
      </SettingsField>

      <div className="pt-3">
        <button
          type="button"
          onClick={() => {
            resetSection("tables");
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Reset tables
        </button>
      </div>
    </div>
  );
}
