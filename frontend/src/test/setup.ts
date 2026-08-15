import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { cleanup, configure } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { resetDecisionCenterStore } from "@/test/msw/decision-center-store";
import { resetWatchlistStore } from "@/test/msw/watchlist-store";

// `waitFor`/`findBy*`'s own default internal timeout (1000ms) is
// independent of vitest's `testTimeout` (30s, vite.config.ts) — a real
// async resolution (React Query -> MSW -> re-render) that takes just
// over 1000ms under real machine load (module transform/setup overhead,
// concurrent processes) times out `waitFor` even though the test itself
// has ample budget remaining. Root-caused via
// `decision-workspace-page.test.tsx`'s own "shows the portfolio's own
// name" case, which failed deterministically under sustained load and
// passed reliably at 5000ms — a pre-existing environment-timing
// sensitivity (not a genuine app race: no code in its dependency chain
// changed), addressed globally here rather than patched per-test, since
// the same 1000ms budget is tight for any test with a real query
// round-trip, not just this one.
configure({ asyncUtilTimeout: 5000 });

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  // jsdom has no layout engine, so `window.scrollTo` is unimplemented —
  // TanStack Router calls it for scroll restoration on every successful
  // navigation. Stub it so that call is a no-op instead of jsdom's
  // default "not implemented" console error.
  window.scrollTo = () => undefined;
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  // Safety net: a test file that seeds the mock watchlist store
  // (`resetWatchlistStore([...])` in its own `beforeEach`) shouldn't
  // leak mutations into a different file that never seeds it.
  resetWatchlistStore();
  resetDecisionCenterStore();
});

afterAll(() => {
  server.close();
});
