import { useId, useState, type ReactNode } from "react";
import { LoadingButton } from "@/components/forms/loading-button";

export interface NotesCellProps {
  ticker: string;
  notes: string | null;
  isSaving: boolean;
  onSave: (ticker: string, notes: string) => void;
}

/** Click-to-edit free text — the notes column only ever holds one field,
 * so a full form dialog would be more ceremony than the data warrants. */
export function NotesCell({ ticker, notes, isSaving, onSave }: NotesCellProps): ReactNode {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(notes ?? "");
  // The adaptive company table mounts a desktop and a mobile NotesCell
  // for the same item simultaneously (CSS picks which is visible) — a
  // plain `notes-${ticker}` id would collide between the two, breaking
  // the label/textarea association for whichever isn't first in the DOM.
  const textareaId = useId();

  if (!editing) {
    return (
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 break-words text-slate-600 dark:text-slate-300">{notes ?? "—"}</p>
        <button
          type="button"
          onClick={() => {
            setDraft(notes ?? "");
            setEditing(true);
          }}
          aria-label={`Edit notes for ${ticker}`}
          className="shrink-0 rounded px-1.5 py-0.5 text-xs text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
        >
          Edit
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={textareaId} className="sr-only">
        Notes for {ticker}
      </label>
      <textarea
        id={textareaId}
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
        }}
        rows={2}
        className="w-full min-w-40 rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
      />
      <div className="flex gap-2">
        <LoadingButton
          type="button"
          isLoading={isSaving}
          onClick={() => {
            onSave(ticker, draft);
            setEditing(false);
          }}
          className="rounded-md bg-brand-600 px-2 py-1 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          Save
        </LoadingButton>
        <button
          type="button"
          onClick={() => {
            setEditing(false);
          }}
          className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
