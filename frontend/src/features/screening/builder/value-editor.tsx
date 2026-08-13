import { useState, type ReactNode } from "react";
import type { ScreenableFieldType } from "@/features/screening/screenable-fields";
import type { ScreenOperator } from "@/types/screening";

const INPUT_CLASS =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

function coerce(raw: string, type: ScreenableFieldType): unknown {
  if (type === "number") {
    if (raw.trim() === "") return null;
    const parsed = Number(raw);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return raw;
}

/** Safe display stringification for a filter's `unknown`-typed value —
 * only ever a `string`, `number`, or `null`/`undefined` in practice
 * (`coerce` above is the only producer), but typed `unknown` since it
 * flows straight from `ScreenFilter.value: unknown`. */
function toDisplayString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return "";
}

export interface ValueEditorProps {
  filterId: string;
  operator: ScreenOperator;
  fieldType: ScreenableFieldType;
  value: unknown;
  onChange: (value: unknown) => void;
}

/** Value shape is entirely dictated by `operator` (mirrors the backend's
 * own `ScreenFilter._validate_field_and_value`): a `[low, high]` pair for
 * BETWEEN, a non-empty array for IN/NOT_IN, a bare scalar otherwise. */
export function ValueEditor({ filterId, operator, fieldType, value, onChange }: ValueEditorProps): ReactNode {
  const inputType = fieldType === "number" ? "number" : "text";

  if (operator === "BETWEEN") {
    const [low, high] = (Array.isArray(value) ? value : [null, null]) as [unknown, unknown];
    return (
      <div className="flex items-center gap-1.5">
        <label className="sr-only" htmlFor={`${filterId}-low`}>
          Low bound
        </label>
        <input
          id={`${filterId}-low`}
          type={inputType}
          value={toDisplayString(low)}
          onChange={(event) => {
            onChange([coerce(event.target.value, fieldType), high ?? null]);
          }}
          className={`${INPUT_CLASS} w-24`}
          placeholder="Low"
        />
        <span aria-hidden="true" className="text-slate-400">
          –
        </span>
        <label className="sr-only" htmlFor={`${filterId}-high`}>
          High bound
        </label>
        <input
          id={`${filterId}-high`}
          type={inputType}
          value={toDisplayString(high)}
          onChange={(event) => {
            onChange([low ?? null, coerce(event.target.value, fieldType)]);
          }}
          className={`${INPUT_CLASS} w-24`}
          placeholder="High"
        />
      </div>
    );
  }

  if (operator === "IN" || operator === "NOT_IN") {
    return <ListValueEditor filterId={filterId} fieldType={fieldType} value={value} onChange={onChange} />;
  }

  return (
    <div>
      <label className="sr-only" htmlFor={`${filterId}-value`}>
        Value
      </label>
      <input
        id={`${filterId}-value`}
        type={inputType}
        value={toDisplayString(value)}
        onChange={(event) => {
          onChange(coerce(event.target.value, fieldType));
        }}
        className={`${INPUT_CLASS} w-32`}
      />
    </div>
  );
}

function ListValueEditor({
  filterId,
  fieldType,
  value,
  onChange,
}: {
  filterId: string;
  fieldType: ScreenableFieldType;
  value: unknown;
  onChange: (value: unknown) => void;
}): ReactNode {
  const [raw, setRaw] = useState(() => (Array.isArray(value) ? value.join(", ") : ""));

  function commit(text: string): void {
    const parsed = text
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item.length > 0)
      .map((item) => coerce(item, fieldType))
      .filter((item) => item !== null);
    onChange(parsed);
  }

  return (
    <div>
      <label className="sr-only" htmlFor={`${filterId}-value`}>
        Comma-separated values
      </label>
      <input
        id={`${filterId}-value`}
        type="text"
        value={raw}
        placeholder="e.g. Technology, Healthcare"
        onChange={(event) => {
          setRaw(event.target.value);
          commit(event.target.value);
        }}
        className={`${INPUT_CLASS} w-48`}
      />
    </div>
  );
}
