import type { ReactNode } from "react";
import type { SortDirection } from "@/types/watchlist";

export interface SortableColumnHeaderProps<TField extends string> {
  label: string;
  field: TField;
  activeField: TField;
  direction: SortDirection;
  onSort: (field: TField) => void;
}

/** A `<th>` that toggles server-side sort on click, with `aria-sort`
 * kept in sync for assistive tech — reusable anywhere a table's columns
 * map onto a backend `sort`/`direction` query param pair. */
export function SortableColumnHeader<TField extends string>({
  label,
  field,
  activeField,
  direction,
  onSort,
}: SortableColumnHeaderProps<TField>): ReactNode {
  const isActive = field === activeField;
  return (
    <th
      scope="col"
      aria-sort={isActive ? (direction === "asc" ? "ascending" : "descending") : "none"}
      className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400"
    >
      <button
        type="button"
        onClick={() => {
          onSort(field);
        }}
        className="flex items-center gap-1 hover:text-slate-900 dark:hover:text-slate-100"
      >
        {label}
        {isActive && <span aria-hidden="true">{direction === "asc" ? "▲" : "▼"}</span>}
      </button>
    </th>
  );
}
