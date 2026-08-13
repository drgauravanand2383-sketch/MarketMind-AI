import type { ReactNode } from "react";
import { SettingsField } from "@/features/settings/settings-field";
import { usePreferencesStore } from "@/store/preferences-store";

export function AccessibilityTab(): ReactNode {
  const accessibility = usePreferencesStore((state) => state.accessibility);
  const setReducedMotion = usePreferencesStore((state) => state.setReducedMotion);
  const setHighContrast = usePreferencesStore((state) => state.setHighContrast);
  const setLargeText = usePreferencesStore((state) => state.setLargeText);
  const setFocusHighlight = usePreferencesStore((state) => state.setFocusHighlight);
  const resetSection = usePreferencesStore((state) => state.resetSection);

  return (
    <div className="flex flex-col">
      <SettingsField label="Reduced motion" description="Also the Appearance tab's Enable animations toggle, inverted.">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={accessibility.reducedMotion}
            onChange={(event) => {
              setReducedMotion(event.target.checked);
            }}
          />
          Reduce motion
        </label>
      </SettingsField>

      <SettingsField label="High contrast" description="Frontend-only — stronger borders and text contrast.">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={accessibility.highContrast}
            onChange={(event) => {
              setHighContrast(event.target.checked);
            }}
          />
          High contrast
        </label>
      </SettingsField>

      <SettingsField label="Larger text">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={accessibility.largeText}
            onChange={(event) => {
              setLargeText(event.target.checked);
            }}
          />
          Larger text
        </label>
      </SettingsField>

      <SettingsField label="Focus highlight" description="A stronger, always-visible outline around the focused element.">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={accessibility.focusHighlight}
            onChange={(event) => {
              setFocusHighlight(event.target.checked);
            }}
          />
          Focus highlight
        </label>
      </SettingsField>

      <div className="pt-3">
        <button
          type="button"
          onClick={() => {
            resetSection("accessibility");
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Reset accessibility
        </button>
      </div>
    </div>
  );
}
