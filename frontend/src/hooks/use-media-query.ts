import { useEffect, useState } from "react";

// jsdom (this project's test environment) doesn't implement
// `window.matchMedia` at all — fall back to `true` rather than `false`
// so a test that never stubs it still sees the same default layout
// (desktop/table) that rendering both layouts unconditionally used to
// produce, instead of every test needing its own stub.
function getMatches(query: string): boolean {
  if (typeof window.matchMedia !== "function") return true;
  return window.matchMedia(query).matches;
}

/** Tracks a CSS media query's match state, following the same
 * `window.matchMedia` + `addEventListener("change", ...)` pattern
 * `theme-store.ts`/`theme-provider.tsx` already use for the OS
 * light/dark preference — reused here so a component can pick one
 * rendered representation of the same data instead of rendering both
 * a desktop and mobile layout simultaneously and hiding one with CSS
 * (a Milestone 9 audit finding on `CompanyTable`, which doubled its DOM
 * node count for the same rows regardless of viewport). */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => getMatches(query));

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(query);
    const handleChange = (): void => {
      setMatches(media.matches);
    };
    handleChange();
    media.addEventListener("change", handleChange);
    return () => {
      media.removeEventListener("change", handleChange);
    };
  }, [query]);

  return matches;
}
