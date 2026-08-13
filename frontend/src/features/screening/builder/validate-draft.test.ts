import { describe, expect, it } from "vitest";
import { validateDraft } from "@/features/screening/builder/validate-draft";
import type { ScreenFilter } from "@/types/screening";

function filter(overrides: Partial<ScreenFilter> = {}): ScreenFilter {
  return { id: "f1", field: "market_cap", operator: "GREATER_THAN", value: 1_000_000, group: null, enabled: true, ...overrides };
}

describe("validateDraft", () => {
  it("passes a well-formed scalar filter", () => {
    expect(validateDraft([filter()], [])).toEqual([]);
  });

  it("flags a scalar filter with no value", () => {
    const errors = validateDraft([filter({ value: null })], []);
    expect(errors).toHaveLength(1);
  });

  it("flags a BETWEEN filter missing a bound", () => {
    const errors = validateDraft([filter({ operator: "BETWEEN", value: [1, null] })], []);
    expect(errors.some((e) => e.includes("between"))).toBe(true);
  });

  it("flags a BETWEEN filter whose low bound exceeds its high bound", () => {
    const errors = validateDraft([filter({ operator: "BETWEEN", value: [100, 10] })], []);
    expect(errors.some((e) => e.includes("low value"))).toBe(true);
  });

  it("passes a well-formed BETWEEN filter", () => {
    expect(validateDraft([filter({ operator: "BETWEEN", value: [10, 100] })], [])).toEqual([]);
  });

  it("flags an empty IN filter", () => {
    const errors = validateDraft([filter({ operator: "IN", value: [] })], []);
    expect(errors).toHaveLength(1);
  });

  it("passes a non-empty IN filter", () => {
    expect(validateDraft([filter({ operator: "IN", value: ["Technology"] })], [])).toEqual([]);
  });

  it("flags a filter assigned to an unknown group", () => {
    const errors = validateDraft([filter({ group: "missing-group" })], []);
    expect(errors.some((e) => e.includes("unknown group"))).toBe(true);
  });

  it("passes a filter assigned to a known group", () => {
    const errors = validateDraft([filter({ group: "g1" })], [{ id: "g1", logic: "AND", parent_group: null }]);
    expect(errors).toEqual([]);
  });

  it("flags a group whose parent would create a cycle", () => {
    const errors = validateDraft(
      [],
      [
        { id: "a", logic: "AND", parent_group: "b" },
        { id: "b", logic: "OR", parent_group: "a" },
      ],
    );
    expect(errors.some((e) => e.includes("cycle"))).toBe(true);
  });
});
