import { useState, type ReactNode } from "react";
import { Button } from "@/components/button";
import { SettingsField } from "@/features/settings/settings-field";
import { SHORTCUT_DEFINITIONS, useShortcutsStore, type ShortcutAction } from "@/store/shortcuts-store";

function RebindCapture({ action, onDone }: { action: ShortcutAction; onDone: () => void }): ReactNode {
  const setBinding = useShortcutsStore((state) => state.setBinding);

  return (
    <input
      autoFocus
      readOnly
      value="Press any key…"
      aria-label={`Press a key to rebind "${action}"`}
      onKeyDown={(event) => {
        event.preventDefault();
        if (event.key !== "Escape") {
          setBinding(action, event.key);
        }
        onDone();
      }}
      onBlur={onDone}
      className="w-32 rounded-md border border-brand-500 px-2 py-1 text-xs text-slate-700 dark:bg-slate-900 dark:text-slate-100"
    />
  );
}

/** Milestone 9 "Keyboard Productivity" — lets a user see and rebind
 * every configurable shortcut. Capture is a single keydown on a
 * temporary, readonly input (no dedicated recording library needed);
 * `Escape` cancels without changing the binding. */
export function ShortcutsTab(): ReactNode {
  const bindings = useShortcutsStore((state) => state.bindings);
  const resetBinding = useShortcutsStore((state) => state.resetBinding);
  const resetAll = useShortcutsStore((state) => state.resetAll);
  const [capturingAction, setCapturingAction] = useState<ShortcutAction | null>(null);

  return (
    <div className="flex flex-col">
      <p className="pb-3 text-sm text-slate-600 dark:text-slate-300">
        Click "Change", then press any key to rebind. Shortcuts are ignored while typing in a text field.
      </p>

      {SHORTCUT_DEFINITIONS.map((definition) => (
        <SettingsField key={definition.action} label={definition.label}>
          <div className="flex items-center gap-2">
            {capturingAction === definition.action ? (
              <RebindCapture
                action={definition.action}
                onDone={() => {
                  setCapturingAction(null);
                }}
              />
            ) : (
              <kbd className="rounded-md border border-slate-300 bg-slate-50 px-2 py-0.5 font-mono text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
                {bindings[definition.action]}
              </kbd>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setCapturingAction(definition.action);
              }}
            >
              Change
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                resetBinding(definition.action);
              }}
            >
              Reset
            </Button>
          </div>
        </SettingsField>
      ))}

      <div className="pt-3">
        <Button variant="secondary" onClick={resetAll}>
          Reset all shortcuts
        </Button>
      </div>
    </div>
  );
}
