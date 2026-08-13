import type { Watchlist, WatchlistItem } from "@/types/watchlist";

/** A tiny in-memory stand-in for the backend's watchlist repository —
 * lets MSW-backed tests exercise real CRUD/filter/sort/pagination
 * request→response round trips instead of one static fixture per
 * endpoint. Mirrors the real backend's own filter/sort semantics
 * (`app.api.v1.schemas.filters`/`pagination`) closely enough for test
 * purposes; it is not a reimplementation of the backend, just enough
 * behavior for the frontend's own tests to be meaningful. */

let watchlists: Watchlist[] = [];
let nextId = 1;

export function resetWatchlistStore(seed: Watchlist[] = []): void {
  watchlists = seed.map((watchlist) => ({ ...watchlist, items: [...watchlist.items] }));
  nextId = 1;
}

function nowIso(): string {
  return new Date().toISOString();
}

export function createWatchlist(name: string, description: string): Watchlist {
  const timestamp = nowIso();
  const watchlist: Watchlist = { id: `test-watchlist-${String(nextId)}`, name, description, created_at: timestamp, updated_at: timestamp, items: [] };
  nextId += 1;
  watchlists.push(watchlist);
  return watchlist;
}

export function getWatchlist(id: string): Watchlist | undefined {
  return watchlists.find((watchlist) => watchlist.id === id);
}

export function renameWatchlist(id: string, name: string): Watchlist | undefined {
  const watchlist = getWatchlist(id);
  if (!watchlist) return undefined;
  watchlist.name = name;
  watchlist.updated_at = nowIso();
  return watchlist;
}

export function deleteWatchlist(id: string): boolean {
  const index = watchlists.findIndex((watchlist) => watchlist.id === id);
  if (index === -1) return false;
  watchlists.splice(index, 1);
  return true;
}

export function hasTicker(id: string, ticker: string): boolean {
  return getWatchlist(id)?.items.some((item) => item.ticker === ticker.toUpperCase()) ?? false;
}

export function addCompany(id: string, item: WatchlistItem): Watchlist | undefined {
  const watchlist = getWatchlist(id);
  if (!watchlist) return undefined;
  watchlist.items.push({ ...item, ticker: item.ticker.toUpperCase() });
  watchlist.updated_at = nowIso();
  return watchlist;
}

export function removeCompany(id: string, ticker: string): Watchlist | undefined {
  const watchlist = getWatchlist(id);
  if (!watchlist) return undefined;
  const normalized = ticker.toUpperCase();
  if (!watchlist.items.some((item) => item.ticker === normalized)) return undefined;
  watchlist.items = watchlist.items.filter((item) => item.ticker !== normalized);
  watchlist.updated_at = nowIso();
  return watchlist;
}

export function updateNotes(id: string, ticker: string, notes: string): Watchlist | undefined {
  const watchlist = getWatchlist(id);
  if (!watchlist) return undefined;
  const normalized = ticker.toUpperCase();
  if (!watchlist.items.some((item) => item.ticker === normalized)) return undefined;
  watchlist.items = watchlist.items.map((item) => (item.ticker === normalized ? { ...item, notes } : item));
  watchlist.updated_at = nowIso();
  return watchlist;
}

export interface WatchlistQuery {
  page: number;
  page_size: number;
  sort: "name" | "created_at" | "updated_at";
  direction: "asc" | "desc";
  name?: string | undefined;
  sector?: string | undefined;
  country?: string | undefined;
  theme?: string | undefined;
  ticker?: string | undefined;
}

export function queryWatchlists(query: WatchlistQuery): { data: Watchlist[]; total: number } {
  let filtered = watchlists;

  if (query.name) {
    const needle = query.name.toLowerCase();
    filtered = filtered.filter((watchlist) => watchlist.name.toLowerCase().includes(needle));
  }

  const itemFiltersActive = query.sector ?? query.country ?? query.theme ?? query.ticker;
  if (itemFiltersActive) {
    filtered = filtered.filter((watchlist) =>
      watchlist.items.some((item) => {
        if (query.sector && (item.sector ?? "").toLowerCase() !== query.sector.toLowerCase()) return false;
        if (query.country && (item.country ?? "").toLowerCase() !== query.country.toLowerCase()) return false;
        if (query.theme && (item.theme ?? "").toLowerCase() !== query.theme.toLowerCase()) return false;
        if (query.ticker && item.ticker !== query.ticker.toUpperCase()) return false;
        return true;
      }),
    );
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
