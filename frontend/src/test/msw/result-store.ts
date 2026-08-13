/** A tiny in-memory id→value cache for MSW handlers — mirrors the real
 * backend's `InMemoryResultStore` (`app.api.v1.schemas.result_store`)
 * closely enough to exercise the POST-then-GET-by-id round trip for
 * Company Research reports and Screening run results, both of which are
 * in-process-only on the real backend too (see
 * `docs/architecture/INTELLIGENCE_API.md` §2). */
export interface ResultStore<T> {
  put: (value: T) => string;
  get: (id: string) => T | undefined;
  reset: () => void;
}

export function createResultStore<T>(prefix: string): ResultStore<T> {
  const store = new Map<string, T>();
  let nextId = 1;

  return {
    put(value: T): string {
      const id = `${prefix}-${String(nextId)}`;
      nextId += 1;
      store.set(id, value);
      return id;
    },
    get(id: string): T | undefined {
      return store.get(id);
    },
    reset(): void {
      store.clear();
      nextId = 1;
    },
  };
}
