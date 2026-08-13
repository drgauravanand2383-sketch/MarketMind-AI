import { useState, type ReactNode } from "react";
import { Button } from "@/components/button";
import { restoreDefaultsFor, useSavedViewsStore } from "@/store/saved-views-store";
import type { SavedViewKind } from "@/types/preferences";

const KIND_LABELS: Record<SavedViewKind, string> = {
  "dashboard-layout": "Dashboard layout",
  "chart-defaults": "Chart preferences",
  "notification-filter": "Notification filter",
};
const KINDS = Object.keys(KIND_LABELS) as SavedViewKind[];

/**
 * Named, reusable snapshots of Milestone 8's own settings only —
 * dashboard layouts, global chart-preference defaults, and the
 * Notification Center's filters. Deliberately does not touch
 * Screening/Alerts/Watchlist filters (approved scope,
 * `docs/frontend/MILESTONE_8.md`).
 */
export function SavedViewsPanel(): ReactNode {
  const views = useSavedViewsStore((state) => state.views);
  const saveView = useSavedViewsStore((state) => state.saveView);
  const applyView = useSavedViewsStore((state) => state.applyView);
  const deleteView = useSavedViewsStore((state) => state.deleteView);

  const [name, setName] = useState("");
  const [kind, setKind] = useState<SavedViewKind>("dashboard-layout");

  function handleSave(): void {
    if (!name.trim()) return;
    saveView(name.trim(), kind);
    setName("");
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="saved-view-name" className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Name
          </label>
          <input
            id="saved-view-name"
            type="text"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
            placeholder="e.g. Compact overview"
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="saved-view-kind" className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Captures
          </label>
          <select
            id="saved-view-kind"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value as SavedViewKind);
            }}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
        </div>
        <Button onClick={handleSave} disabled={!name.trim()}>
          Save current as…
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        {KINDS.map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => {
              restoreDefaultsFor(k);
            }}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Restore default {KIND_LABELS[k].toLowerCase()}
          </button>
        ))}
      </div>

      {views.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">No saved views yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {views.map((view) => (
            <li key={view.id} className="flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800">
              <div>
                <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{view.name}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {KIND_LABELS[view.kind]} · {new Date(view.createdAt).toLocaleString()}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    applyView(view.id);
                  }}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Apply
                </button>
                <button
                  type="button"
                  onClick={() => {
                    deleteView(view.id);
                  }}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:border-slate-700 dark:text-red-400 dark:hover:bg-red-950"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
