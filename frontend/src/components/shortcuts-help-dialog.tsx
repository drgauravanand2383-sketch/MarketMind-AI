import type { ReactNode } from "react";
import { Dialog } from "@/components/dialog";
import { SHORTCUT_DEFINITIONS, useShortcutsStore } from "@/store/shortcuts-store";

/** Opened by the "help" shortcut (default `?`) or a future help trigger
 * — mounted once in `AppShell` alongside `useKeyboardShortcuts`, reading
 * `shortcuts-store.ts`'s `helpOpen` flag rather than owning its own
 * open/close state, so any future trigger just calls `openHelp()`. */
export function ShortcutsHelpDialog(): ReactNode {
  const open = useShortcutsStore((state) => state.helpOpen);
  const closeHelp = useShortcutsStore((state) => state.closeHelp);
  const bindings = useShortcutsStore((state) => state.bindings);

  return (
    <Dialog open={open} onClose={closeHelp} title="Keyboard shortcuts">
      <ul className="flex flex-col gap-2">
        {SHORTCUT_DEFINITIONS.map((definition) => (
          <li key={definition.action} className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-700 dark:text-slate-300">{definition.label}</span>
            <kbd className="rounded-md border border-slate-300 bg-slate-50 px-2 py-0.5 font-mono text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
              {bindings[definition.action]}
            </kbd>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Shortcuts are ignored while typing in a text field. Rebind them in Workspace Settings → Shortcuts.
      </p>
    </Dialog>
  );
}
