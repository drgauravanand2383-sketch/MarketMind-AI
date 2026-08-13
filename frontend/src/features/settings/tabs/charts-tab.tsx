import type { ReactNode } from "react";
import { SettingsField } from "@/features/settings/settings-field";
import { usePreferencesStore } from "@/store/preferences-store";

export function ChartsTab(): ReactNode {
  const showDataLabels = usePreferencesStore((state) => state.charts.showDataLabels);
  const setShowDataLabels = usePreferencesStore((state) => state.setShowDataLabels);
  const resetSection = usePreferencesStore((state) => state.resetSection);

  return (
    <div className="flex flex-col">
      <SettingsField label="Show chart data labels by default" description="Applies to charts across the Decision Center and Historical Analysis Center — each chart's own toggle still overrides this per view.">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={showDataLabels}
            onChange={(event) => {
              setShowDataLabels(event.target.checked);
            }}
          />
          Show labels
        </label>
      </SettingsField>

      <div className="pt-3">
        <button
          type="button"
          onClick={() => {
            resetSection("charts");
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Reset charts
        </button>
      </div>
    </div>
  );
}
