import type { ReportCategory } from "@/types/global-markets";

/** Mirrors `REPORT_CATEGORY_DEFINITIONS[*].display_name`
 * (`app/global_markets/models.py`) exactly. Hardcoded (not fetched via
 * `useCategories()`) so every tab/panel title renders immediately with
 * no loading flash — the same convention `lib/nav-items.ts` already
 * uses for every other feature's nav label. The single source every
 * Global Markets component reads a category's display name from. */
export const CATEGORY_DISPLAY_NAMES: Record<ReportCategory, string> = {
  INDIA_EQUITY: "India Stocks",
  US_EQUITY: "US Stocks",
  CHINA_EQUITY: "China Stocks",
  FOREX: "Forex",
  CRYPTO: "Major Crypto",
  INDIA_PENNY_STOCK: "India Penny Stocks",
  US_PENNY_STOCK: "US Penny Stocks",
  CHINA_PENNY_STOCK: "China Penny Stocks",
  LOW_CAP_CRYPTO: "Low-Cap Crypto Discovery",
};
