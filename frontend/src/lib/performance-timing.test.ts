import { afterEach, describe, expect, it } from "vitest";
import { markAppShellMounted, markBootStart } from "@/lib/performance-timing";

describe("performance-timing", () => {
  afterEach(() => {
    performance.clearMarks();
    performance.clearMeasures();
  });

  it("markBootStart records a named performance mark", () => {
    markBootStart();

    expect(performance.getEntriesByName("marketmind:boot-start")).toHaveLength(1);
  });

  it("markAppShellMounted records a mark and a measure when boot-start already ran", () => {
    markBootStart();

    markAppShellMounted();

    expect(performance.getEntriesByName("marketmind:app-shell-mounted")).toHaveLength(1);
    expect(performance.getEntriesByName("marketmind:boot-to-shell")).toHaveLength(1);
  });

  it("markAppShellMounted records only the mark, no measure, if boot-start never ran", () => {
    markAppShellMounted();

    expect(performance.getEntriesByName("marketmind:app-shell-mounted")).toHaveLength(1);
    expect(performance.getEntriesByName("marketmind:boot-to-shell")).toHaveLength(0);
  });
});
