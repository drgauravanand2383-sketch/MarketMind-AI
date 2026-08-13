import { useRef, useState, type ReactNode } from "react";
import { downloadPreferencesExport, importPreferencesFromJson } from "@/lib/preferences-io";

/** Export = a real client-side file download (`Blob` + `URL
 * .createObjectURL`, no server round trip). Import validates with `zod`
 * before writing anything to any store — an invalid file is rejected
 * with a readable message and never partially applied (see
 * `lib/preferences-io.ts`'s own docstring on why that satisfies
 * "rollback on invalid import" without a separate undo step). */
export function ImportExportPanel(): ReactNode {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    const text = await file.text();
    const result = importPreferencesFromJson(text);
    setMessage(result.success ? { type: "success", text: "Preferences imported successfully." } : { type: "error", text: result.error });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={downloadPreferencesExport}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Export preferences
        </button>
        <button
          type="button"
          onClick={() => {
            fileInputRef.current?.click();
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Import preferences
        </button>
        <label className="sr-only" htmlFor="preferences-import-file">
          Import preferences file
        </label>
        <input
          ref={fileInputRef}
          id="preferences-import-file"
          type="file"
          accept="application/json"
          className="sr-only"
          onChange={(event) => {
            void handleFileSelected(event);
          }}
        />
      </div>
      {message && (
        <p role="status" className={message.type === "success" ? "text-sm text-green-700 dark:text-green-400" : "text-sm text-red-600 dark:text-red-400"}>
          {message.text}
        </p>
      )}
    </div>
  );
}
