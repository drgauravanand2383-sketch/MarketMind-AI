import type { LogicalGroup, ScreenFilter, ScreeningProfile } from "@/types/screening";

/** A tiny in-memory stand-in for `ScreeningEngine`'s profile repository —
 * mirrors `test/msw/watchlist-store.ts`'s role for screening profiles,
 * including the Frontend Milestone 4 `name` filter and duplicate
 * endpoint additions. */

let profiles: ScreeningProfile[] = [];
let nextId = 1;

export function resetScreeningStore(seed: ScreeningProfile[] = []): void {
  profiles = seed.map((profile) => ({ ...profile, filters: [...profile.filters], groups: [...profile.groups] }));
  nextId = 1;
}

function nowIso(): string {
  return new Date().toISOString();
}

export function createScreeningProfile(
  name: string,
  description: string,
  filters: ScreenFilter[] = [],
  groups: LogicalGroup[] = [],
): ScreeningProfile {
  const timestamp = nowIso();
  const profile: ScreeningProfile = {
    id: `test-profile-${String(nextId)}`,
    name,
    description,
    created_at: timestamp,
    updated_at: timestamp,
    is_default: false,
    filters,
    groups,
  };
  nextId += 1;
  profiles.push(profile);
  return profile;
}

export function getScreeningProfile(id: string): ScreeningProfile | undefined {
  return profiles.find((profile) => profile.id === id);
}

export function nameTaken(name: string): boolean {
  return profiles.some((profile) => profile.name === name);
}

export function updateScreeningProfile(id: string, patch: Partial<ScreeningProfile>): ScreeningProfile | undefined {
  const profile = getScreeningProfile(id);
  if (!profile) return undefined;
  Object.assign(profile, patch, { updated_at: nowIso() });
  return profile;
}

export function deleteScreeningProfile(id: string): boolean {
  const index = profiles.findIndex((profile) => profile.id === id);
  if (index === -1) return false;
  profiles.splice(index, 1);
  return true;
}

export function duplicateScreeningProfile(id: string, newName: string): ScreeningProfile | "not_found" | "conflict" {
  const source = getScreeningProfile(id);
  if (!source) return "not_found";
  if (nameTaken(newName)) return "conflict";
  return createScreeningProfile(newName, source.description, [...source.filters], [...source.groups]);
}

export interface ScreeningProfileQuery {
  page: number;
  page_size: number;
  sort: "name" | "created_at" | "updated_at";
  direction: "asc" | "desc";
  name?: string | undefined;
}

export function queryScreeningProfiles(query: ScreeningProfileQuery): { data: ScreeningProfile[]; total: number } {
  let filtered = profiles;

  if (query.name) {
    const needle = query.name.toLowerCase();
    filtered = filtered.filter((profile) => profile.name.toLowerCase().includes(needle));
  }

  const sorted = [...filtered].sort((a, b) => {
    const left = query.sort === "name" ? a.name.toLowerCase() : a[query.sort];
    const right = query.sort === "name" ? b.name.toLowerCase() : b[query.sort];
    const comparison = left < right ? -1 : left > right ? 1 : 0;
    return query.direction === "asc" ? comparison : -comparison;
  });

  const total = sorted.length;
  const start = (query.page - 1) * query.page_size;
  const data = sorted.slice(start, start + query.page_size);
  return { data, total };
}
