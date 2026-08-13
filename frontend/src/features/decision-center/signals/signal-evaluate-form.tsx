import { useState, type ReactNode } from "react";
import { LoadingButton } from "@/components/forms/loading-button";
import { signalableFieldDef, signalableFieldLabel } from "@/features/decision-center/signals/signalable-fields";
import type { MarketDataSnapshot, SignalDefinition } from "@/types/signals";

const INPUT_CLASS =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

interface DraftRow {
  key: string;
  ticker: string;
  company_name: string;
  values: Record<string, string>;
}

function emptyRow(paths: string[]): DraftRow {
  return { key: crypto.randomUUID(), ticker: "", company_name: "", values: Object.fromEntries(paths.map((path) => [path, ""])) };
}

function parseInput(raw: string, type: "number" | "string"): string | number | undefined {
  if (raw.trim() === "") return undefined;
  if (type === "number") {
    const parsed = Number(raw);
    return Number.isNaN(parsed) ? undefined : parsed;
  }
  return raw;
}

function buildSnapshot(row: DraftRow, paths: string[]): MarketDataSnapshot {
  const snapshot: MarketDataSnapshot = { ticker: row.ticker.toUpperCase(), company_name: row.company_name || null };
  const byNamespace: Record<string, Record<string, unknown>> = {};
  for (const path of paths) {
    const def = signalableFieldDef(path);
    if (!def) continue;
    const parsed = parseInput(row.values[path] ?? "", def.type);
    if (parsed === undefined) continue;
    const bucket = (byNamespace[def.namespace] ??= {});
    bucket[def.field] = parsed;
  }
  for (const [namespace, fields] of Object.entries(byNamespace)) {
    if (namespace === "quote") {
      // `MarketQuote.price` is required (`gt=0`) even if no condition
      // actually references it — a placeholder keeps the snapshot valid
      // without misrepresenting a value the user never entered as
      // something meaningful.
      (snapshot as unknown as Record<string, unknown>).quote = { ticker: snapshot.ticker, price: 0.01, timestamp: new Date().toISOString(), ...fields };
    } else if (namespace === "profile") {
      (snapshot as unknown as Record<string, unknown>).profile = { ticker: snapshot.ticker, company_name: row.company_name || snapshot.ticker, ...fields };
    } else {
      (snapshot as unknown as Record<string, unknown>)[namespace] = fields;
    }
  }
  return snapshot;
}

/** Scoped down to only the dotted-path fields the selected definition's
 * own conditions reference (derived from `definition.conditions`), not
 * every field across all four Market Data namespaces — mirrors
 * Milestone 4's `RunScreeningPanel` scoping pattern for the identical
 * reason (usability; the engine only reads what the conditions ask for). */
export function SignalEvaluateForm({
  definition,
  isPending,
  onSubmit,
}: {
  definition: SignalDefinition;
  isPending: boolean;
  onSubmit: (snapshots: MarketDataSnapshot[]) => void;
}): ReactNode {
  const relevantPaths = [...new Set(definition.conditions.map((c) => c.field))];
  const [rows, setRows] = useState<DraftRow[]>(() => [emptyRow(relevantPaths)]);

  function updateRow(key: string, patch: Partial<DraftRow>): void {
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function updateValue(key: string, path: string, raw: string): void {
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, values: { ...row.values, [path]: raw } } : row)));
  }

  const canSubmit = rows.every((row) => row.ticker.trim().length > 0);

  return (
    <div className="flex flex-col gap-4">
      {relevantPaths.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">This definition has no conditions to supply data for.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Companies to evaluate</caption>
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800">
                <th scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Ticker
                </th>
                <th scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Company name
                </th>
                {relevantPaths.map((path) => (
                  <th key={path} scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {signalableFieldLabel(path)}
                  </th>
                ))}
                <th scope="col" className="px-2 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-b border-slate-100 dark:border-slate-800/60">
                  <td className="px-2 py-1.5">
                    <label className="sr-only" htmlFor={`${row.key}-ticker`}>
                      Ticker
                    </label>
                    <input
                      id={`${row.key}-ticker`}
                      value={row.ticker}
                      onChange={(event) => {
                        updateRow(row.key, { ticker: event.target.value });
                      }}
                      className={`${INPUT_CLASS} w-20`}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <label className="sr-only" htmlFor={`${row.key}-name`}>
                      Company name
                    </label>
                    <input
                      id={`${row.key}-name`}
                      value={row.company_name}
                      onChange={(event) => {
                        updateRow(row.key, { company_name: event.target.value });
                      }}
                      className={`${INPUT_CLASS} w-40`}
                    />
                  </td>
                  {relevantPaths.map((path) => {
                    const def = signalableFieldDef(path);
                    return (
                      <td key={path} className="px-2 py-1.5">
                        <label className="sr-only" htmlFor={`${row.key}-${path}`}>
                          {signalableFieldLabel(path)}
                        </label>
                        <input
                          id={`${row.key}-${path}`}
                          type={def?.type === "number" ? "number" : "text"}
                          value={row.values[path] ?? ""}
                          onChange={(event) => {
                            updateValue(row.key, path, event.target.value);
                          }}
                          className={`${INPUT_CLASS} w-24`}
                        />
                      </td>
                    );
                  })}
                  <td className="px-2 py-1.5">
                    <button
                      type="button"
                      onClick={() => {
                        setRows((prev) => prev.filter((r) => r.key !== row.key));
                      }}
                      disabled={rows.length <= 1}
                      aria-label="Remove company"
                      className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-40 dark:text-red-400 dark:hover:bg-red-950"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            setRows((prev) => [...prev, emptyRow(relevantPaths)]);
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Add company
        </button>
        <LoadingButton
          type="button"
          isLoading={isPending}
          loadingText="Evaluating…"
          disabled={!canSubmit}
          onClick={() => {
            onSubmit(rows.map((row) => buildSnapshot(row, relevantPaths)));
          }}
        >
          Evaluate signal
        </LoadingButton>
      </div>
    </div>
  );
}
