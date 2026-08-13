import type { ReactNode } from "react";
import { SCREENABLE_FIELDS, screenableFieldType } from "@/features/screening/screenable-fields";
import { ValueEditor } from "@/features/screening/builder/value-editor";
import { SCREEN_OPERATORS, type LogicalGroup, type ScreenFilter, type ScreenOperator } from "@/types/screening";

const SELECT_CLASS =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

const OPERATOR_LABELS: Record<ScreenOperator, string> = {
  EQUALS: "=",
  NOT_EQUALS: "≠",
  GREATER_THAN: ">",
  GREATER_EQUAL: "≥",
  LESS_THAN: "<",
  LESS_EQUAL: "≤",
  BETWEEN: "between",
  IN: "in",
  NOT_IN: "not in",
};

function defaultValueForOperator(operator: ScreenOperator): unknown {
  if (operator === "BETWEEN") return [null, null];
  if (operator === "IN" || operator === "NOT_IN") return [];
  return null;
}

export interface FilterRowProps {
  filter: ScreenFilter;
  index: number;
  groups: LogicalGroup[];
  canMoveUp: boolean;
  canMoveDown: boolean;
  onChange: (updated: ScreenFilter) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

export function FilterRow({
  filter,
  index,
  groups,
  canMoveUp,
  canMoveDown,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: FilterRowProps): ReactNode {
  const fieldType = screenableFieldType(filter.field);

  return (
    <li
      className={`flex flex-wrap items-center gap-2 rounded-md border p-2 ${
        filter.enabled
          ? "border-slate-200 dark:border-slate-800"
          : "border-slate-100 opacity-60 dark:border-slate-900"
      }`}
    >
      <span className="sr-only">Filter {index + 1}</span>

      <label className="sr-only" htmlFor={`${filter.id}-field`}>
        Field
      </label>
      <select
        id={`${filter.id}-field`}
        value={filter.field}
        onChange={(event) => {
          onChange({ ...filter, field: event.target.value });
        }}
        className={SELECT_CLASS}
      >
        {SCREENABLE_FIELDS.map((def) => (
          <option key={def.field} value={def.field}>
            {def.label}
          </option>
        ))}
      </select>

      <label className="sr-only" htmlFor={`${filter.id}-operator`}>
        Operator
      </label>
      <select
        id={`${filter.id}-operator`}
        value={filter.operator}
        onChange={(event) => {
          const operator = event.target.value as ScreenOperator;
          onChange({ ...filter, operator, value: defaultValueForOperator(operator) });
        }}
        className={SELECT_CLASS}
      >
        {SCREEN_OPERATORS.map((operator) => (
          <option key={operator} value={operator}>
            {OPERATOR_LABELS[operator]}
          </option>
        ))}
      </select>

      <ValueEditor
        filterId={filter.id}
        operator={filter.operator}
        fieldType={fieldType}
        value={filter.value}
        onChange={(value) => {
          onChange({ ...filter, value });
        }}
      />

      {groups.length > 0 && (
        <>
          <label className="sr-only" htmlFor={`${filter.id}-group`}>
            Group
          </label>
          <select
            id={`${filter.id}-group`}
            value={filter.group ?? ""}
            onChange={(event) => {
              onChange({ ...filter, group: event.target.value === "" ? null : event.target.value });
            }}
            className={SELECT_CLASS}
          >
            <option value="">Ungrouped (AND)</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                Group: {group.id} ({group.logic})
              </option>
            ))}
          </select>
        </>
      )}

      <div className="ml-auto flex items-center gap-1">
        <label className="flex items-center gap-1 text-xs text-slate-600 dark:text-slate-300">
          <input
            type="checkbox"
            checked={filter.enabled}
            onChange={(event) => {
              onChange({ ...filter, enabled: event.target.checked });
            }}
          />
          Enabled
        </label>
        <button
          type="button"
          onClick={onMoveUp}
          disabled={!canMoveUp}
          aria-label={`Move filter ${String(index + 1)} up`}
          className="rounded-md px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-30 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          ▲
        </button>
        <button
          type="button"
          onClick={onMoveDown}
          disabled={!canMoveDown}
          aria-label={`Move filter ${String(index + 1)} down`}
          className="rounded-md px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-30 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          ▼
        </button>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove filter ${String(index + 1)}`}
          className="rounded-md px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
        >
          Remove
        </button>
      </div>
    </li>
  );
}
