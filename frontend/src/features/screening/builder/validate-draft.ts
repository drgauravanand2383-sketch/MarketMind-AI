import { wouldCreateCycle } from "@/features/screening/builder/group-utils";
import type { LogicalGroup, ScreenFilter } from "@/types/screening";

/** Client-side mirror of the backend's own `model_validator`s
 * (`ScreenFilter._validate_field_and_value`, `ScreeningProfile._validate_structure`,
 * `_detect_group_cycle` — `app/screening/models.py`) so a builder save
 * fails fast in the UI instead of round-tripping to a 422. The backend
 * remains the source of truth; this is a UX convenience only. */
export function validateDraft(filters: ScreenFilter[], groups: LogicalGroup[]): string[] {
  const errors: string[] = [];
  const groupIds = new Set(groups.map((g) => g.id));

  for (const filter of filters) {
    if (filter.operator === "BETWEEN") {
      const value = filter.value;
      if (!Array.isArray(value) || value.length !== 2 || value[0] === null || value[1] === null) {
        errors.push(`"${filter.field}" (between) needs both a low and a high value.`);
      } else if (typeof value[0] === "number" && typeof value[1] === "number" && value[0] > value[1]) {
        errors.push(`"${filter.field}" (between) — the low value can't exceed the high value.`);
      }
    } else if (filter.operator === "IN" || filter.operator === "NOT_IN") {
      if (!Array.isArray(filter.value) || filter.value.length === 0) {
        errors.push(`"${filter.field}" (${filter.operator.toLowerCase()}) needs at least one value.`);
      }
    } else if (filter.value === null || filter.value === undefined || filter.value === "") {
      errors.push(`"${filter.field}" needs a value.`);
    }

    if (filter.group !== null && filter.group !== undefined && !groupIds.has(filter.group)) {
      errors.push(`"${filter.field}" is assigned to an unknown group.`);
    }
  }

  for (const group of groups) {
    if (group.parent_group != null && wouldCreateCycle(groups, group.id, group.parent_group)) {
      errors.push(`Group "${group.id}"'s parent would create a cycle.`);
    }
  }

  return errors;
}
