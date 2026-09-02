import { describe, expect, it } from "vitest";
import { daysSinceRunDate, formatRunTimestampIst } from "@/features/global-markets/run-timestamp";

describe("formatRunTimestampIst", () => {
  it("renders an ISO instant in Asia/Kolkata with an explicit IST suffix", () => {
    // 03:05 UTC + 5:30 = 08:35 IST on the same day.
    const formatted = formatRunTimestampIst("2026-02-01T03:05:00Z");
    expect(formatted).toMatch(/IST$/);
    expect(formatted).toContain("2026");
    expect(formatted).toMatch(/8:35/);
  });

  it("returns null for a missing or invalid timestamp", () => {
    expect(formatRunTimestampIst(null)).toBeNull();
    expect(formatRunTimestampIst(undefined)).toBeNull();
    expect(formatRunTimestampIst("not-a-date")).toBeNull();
  });
});

describe("daysSinceRunDate", () => {
  it("counts whole days between the run date and now", () => {
    const now = new Date("2026-02-10T09:00:00");
    expect(daysSinceRunDate("2026-02-10", now)).toBe(0);
    expect(daysSinceRunDate("2026-02-08", now)).toBe(2);
  });

  it("never returns a negative count for a future or malformed date", () => {
    const now = new Date("2026-02-10T09:00:00");
    expect(daysSinceRunDate("2026-03-01", now)).toBe(0);
    expect(daysSinceRunDate("garbage", now)).toBe(0);
  });
});
