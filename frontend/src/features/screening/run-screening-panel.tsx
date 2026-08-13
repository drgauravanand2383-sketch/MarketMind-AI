import { useState, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { LoadingButton } from "@/components/forms/loading-button";
import { EmptyState } from "@/components/states/empty-state";
import { parseFieldInput, screenableFieldLabel, screenableFieldType } from "@/features/screening/screenable-fields";
import { useRunScreening } from "@/hooks/use-screening";
import type { CompanyMetrics, ScreeningProfile } from "@/types/screening";

const INPUT_CLASS =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

interface DraftRow {
  key: string;
  ticker: string;
  company_name: string;
  values: Record<string, string>;
}

function emptyRow(fields: string[]): DraftRow {
  return {
    key: crypto.randomUUID(),
    ticker: "",
    company_name: "",
    values: Object.fromEntries(fields.map((field) => [field, ""])),
  };
}

/** No company search/lookup backend endpoint exists — metric values are
 * plain manual entry, scoped down to just the fields this profile's own
 * filters reference (not all ~30 `CompanyMetrics` fields), since that's
 * all `ScreeningEngine.evaluate_companies()` will actually read. */
export function RunScreeningPanel({ profile }: { profile: ScreeningProfile }): ReactNode {
  const navigate = useNavigate();
  const runScreening = useRunScreening(profile.name);
  const relevantFields = [...new Set(profile.filters.map((f) => f.field))];

  const [rows, setRows] = useState<DraftRow[]>(() => [emptyRow(relevantFields)]);

  if (profile.filters.length === 0) {
    return <EmptyState icon="🧮" title="Add filters before running this screen" description="This screen has no filters yet — add at least one in the builder above." />;
  }

  function updateRow(key: string, patch: Partial<DraftRow>): void {
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function updateRowValue(key: string, field: string, raw: string): void {
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, values: { ...row.values, [field]: raw } } : row)));
  }

  function submit(): void {
    const companies: CompanyMetrics[] = rows.map((row) => {
      const metrics: CompanyMetrics = { ticker: row.ticker.toUpperCase(), company_name: row.company_name };
      for (const field of relevantFields) {
        const parsed = parseFieldInput(row.values[field] ?? "", screenableFieldType(field));
        if (parsed !== undefined) {
          (metrics as Record<string, unknown>)[field] = parsed;
        }
      }
      return metrics;
    });

    runScreening.mutate(
      { profile_id: profile.id, companies },
      {
        onSuccess: (envelope) => {
          void navigate({ to: "/screening/results/$resultId", params: { resultId: envelope.result_id } });
        },
      },
    );
  }

  const canSubmit = rows.every((row) => row.ticker.trim().length > 0 && row.company_name.trim().length > 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Companies to screen</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Ticker
              </th>
              <th scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Company name
              </th>
              {relevantFields.map((field) => (
                <th key={field} scope="col" className="px-2 py-1.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  {screenableFieldLabel(field)}
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
                {relevantFields.map((field) => (
                  <td key={field} className="px-2 py-1.5">
                    <label className="sr-only" htmlFor={`${row.key}-${field}`}>
                      {screenableFieldLabel(field)}
                    </label>
                    <input
                      id={`${row.key}-${field}`}
                      type={screenableFieldType(field) === "number" ? "number" : "text"}
                      value={row.values[field] ?? ""}
                      onChange={(event) => {
                        updateRowValue(row.key, field, event.target.value);
                      }}
                      className={`${INPUT_CLASS} w-28`}
                    />
                  </td>
                ))}
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

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            setRows((prev) => [...prev, emptyRow(relevantFields)]);
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Add company
        </button>
        <LoadingButton
          type="button"
          isLoading={runScreening.isPending}
          loadingText="Running…"
          disabled={!canSubmit}
          onClick={submit}
        >
          Run screening
        </LoadingButton>
        {runScreening.isPending && (
          <p role="status" aria-live="polite" className="text-sm text-slate-500 dark:text-slate-400">
            Screening {rows.length} {rows.length === 1 ? "company" : "companies"}…
          </p>
        )}
      </div>
    </div>
  );
}
