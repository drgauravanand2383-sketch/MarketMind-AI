import { describe, expect, it } from "vitest";
import { wouldCreateCycle } from "@/features/screening/builder/group-utils";
import type { LogicalGroup } from "@/types/screening";

describe("wouldCreateCycle", () => {
  const groups: LogicalGroup[] = [
    { id: "a", logic: "AND", parent_group: null },
    { id: "b", logic: "OR", parent_group: "a" },
    { id: "c", logic: "AND", parent_group: "b" },
  ];

  it("allows a top-level (null) parent", () => {
    expect(wouldCreateCycle(groups, "a", null)).toBe(false);
  });

  it("rejects a group being its own parent", () => {
    expect(wouldCreateCycle(groups, "a", "a")).toBe(true);
  });

  it("rejects a parent that is already a descendant (would create a cycle)", () => {
    // "a" -> "b" -> "c" already; making "a"'s parent "c" would close the loop.
    expect(wouldCreateCycle(groups, "a", "c")).toBe(true);
  });

  it("allows a parent that is not an ancestor or descendant", () => {
    const wider: LogicalGroup[] = [...groups, { id: "d", logic: "AND", parent_group: null }];
    expect(wouldCreateCycle(wider, "a", "d")).toBe(false);
  });
});
