import type { CompanyMetrics } from "@/types/screening";

export type ScreenableFieldType = "number" | "string";

export interface ScreenableFieldDef {
  field: keyof CompanyMetrics;
  label: string;
  type: ScreenableFieldType;
}

/** Every field a `ScreenFilter` may legally reference — the backend's own
 * `model_validator` rejects any `field` not in `CompanyMetrics.model_fields`
 * (`app/screening/models.py`), so this list must stay in exact sync with
 * that model. Excludes `ticker`/`company_name` (identity, not screenable
 * criteria). */
export const SCREENABLE_FIELDS: ScreenableFieldDef[] = [
  { field: "country", label: "Country", type: "string" },
  { field: "sector", label: "Sector", type: "string" },
  { field: "industry", label: "Industry", type: "string" },
  { field: "market_cap", label: "Market cap", type: "number" },
  { field: "price", label: "Price", type: "number" },
  { field: "pe_ratio", label: "P/E ratio", type: "number" },
  { field: "forward_pe", label: "Forward P/E", type: "number" },
  { field: "pb_ratio", label: "Price / book", type: "number" },
  { field: "ps_ratio", label: "Price / sales", type: "number" },
  { field: "ev_ebitda", label: "EV / EBITDA", type: "number" },
  { field: "revenue_growth", label: "Revenue growth", type: "number" },
  { field: "earnings_growth", label: "Earnings growth", type: "number" },
  { field: "eps_growth", label: "EPS growth", type: "number" },
  { field: "gross_margin", label: "Gross margin", type: "number" },
  { field: "operating_margin", label: "Operating margin", type: "number" },
  { field: "net_margin", label: "Net margin", type: "number" },
  { field: "roe", label: "ROE", type: "number" },
  { field: "roa", label: "ROA", type: "number" },
  { field: "roic", label: "ROIC", type: "number" },
  { field: "debt_to_equity", label: "Debt / equity", type: "number" },
  { field: "current_ratio", label: "Current ratio", type: "number" },
  { field: "quick_ratio", label: "Quick ratio", type: "number" },
  { field: "free_cash_flow", label: "Free cash flow", type: "number" },
  { field: "fcf_margin", label: "FCF margin", type: "number" },
  { field: "dividend_yield", label: "Dividend yield", type: "number" },
  { field: "payout_ratio", label: "Payout ratio", type: "number" },
  { field: "beta", label: "Beta", type: "number" },
  { field: "volatility", label: "Volatility", type: "number" },
  { field: "analyst_rating", label: "Analyst rating", type: "string" },
  { field: "analyst_target_upside", label: "Analyst target upside", type: "number" },
  { field: "insider_ownership", label: "Insider ownership", type: "number" },
  { field: "institutional_ownership", label: "Institutional ownership", type: "number" },
];

export function screenableFieldLabel(field: string): string {
  return SCREENABLE_FIELDS.find((f) => f.field === field)?.label ?? field;
}

export function screenableFieldType(field: string): ScreenableFieldType {
  return SCREENABLE_FIELDS.find((f) => f.field === field)?.type ?? "number";
}

/** Parses one raw text-input value into what belongs on a `CompanyMetrics`
 * instance for the "run screening" company-entry form — `undefined` (the
 * field omitted from the request) for a blank/unparseable input, since
 * every metric field is optional there. */
export function parseFieldInput(raw: string, type: ScreenableFieldType): string | number | undefined {
  if (raw.trim() === "") return undefined;
  if (type === "number") {
    const parsed = Number(raw);
    return Number.isNaN(parsed) ? undefined : parsed;
  }
  return raw;
}
