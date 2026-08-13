import type { LogicalGroup } from "@/types/screening";

/** Mirrors the backend's own cycle check (`_detect_group_cycle` in
 * `app/screening/models.py`) — walks the candidate parent's own ancestor
 * chain looking for `groupId`. The builder must never let a save reach
 * the backend with a cycle already baked in. */
export function wouldCreateCycle(groups: LogicalGroup[], groupId: string, candidateParentId: string | null): boolean {
  if (candidateParentId === null) return false;
  if (candidateParentId === groupId) return true;

  const parentOf = new Map(groups.map((g) => [g.id, g.parent_group]));
  let current: string | null = candidateParentId;
  const visited = new Set<string>();
  while (current !== null) {
    if (current === groupId) return true;
    if (visited.has(current)) return false;
    visited.add(current);
    current = parentOf.get(current) ?? null;
  }
  return false;
}

export function generateGroupId(): string {
  return `group-${crypto.randomUUID().slice(0, 8)}`;
}

export function generateFilterId(): string {
  return `filter-${crypto.randomUUID().slice(0, 8)}`;
}
