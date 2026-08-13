/** Builds a `?a=1&b=2` query string from a flat params object, dropping
 * `undefined`/`""` entries — used by every API module that needs to
 * forward pagination/filter/sort params onto a GET request, since
 * `ApiClient` takes a raw path string and does no query-building itself. */
export function buildQueryString(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}
