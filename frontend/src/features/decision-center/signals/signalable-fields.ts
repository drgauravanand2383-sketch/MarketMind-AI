export type SignalableFieldType = "number" | "string";

export interface SignalableFieldDef {
  /** `"<namespace>.<field>"` — the exact dotted path `SignalCondition.field` expects. */
  path: string;
  namespace: "quote" | "profile" | "fundamentals" | "ratios";
  field: string;
  label: string;
  type: SignalableFieldType;
}

/** Every field a `SignalCondition` may legally reference — the backend's
 * own `model_validator` rejects any `field` not matching
 * `"<namespace>.<name>"` where `name` is a real field on that namespace's
 * Market Data Abstraction Layer model (`app/signals/models.py`). Mirrors
 * Milestone 4's `screenable-fields.ts` role for Screening's flat
 * `CompanyMetrics` — this list must stay in exact sync with
 * `MarketQuote`/`CompanyProfile`/`FinancialRatios`/`Fundamentals`. */
export const SIGNALABLE_FIELDS: SignalableFieldDef[] = [
  // quote.*
  { path: "quote.price", namespace: "quote", field: "price", label: "Price", type: "number" },
  { path: "quote.change", namespace: "quote", field: "change", label: "Change", type: "number" },
  { path: "quote.change_percent", namespace: "quote", field: "change_percent", label: "Change %", type: "number" },
  { path: "quote.volume", namespace: "quote", field: "volume", label: "Volume", type: "number" },
  { path: "quote.average_volume", namespace: "quote", field: "average_volume", label: "Average volume", type: "number" },
  { path: "quote.previous_close", namespace: "quote", field: "previous_close", label: "Previous close", type: "number" },
  { path: "quote.open", namespace: "quote", field: "open", label: "Open", type: "number" },
  { path: "quote.day_high", namespace: "quote", field: "day_high", label: "Day high", type: "number" },
  { path: "quote.day_low", namespace: "quote", field: "day_low", label: "Day low", type: "number" },
  { path: "quote.currency", namespace: "quote", field: "currency", label: "Currency (quote)", type: "string" },
  { path: "quote.exchange", namespace: "quote", field: "exchange", label: "Exchange (quote)", type: "string" },
  // profile.*
  { path: "profile.country", namespace: "profile", field: "country", label: "Country", type: "string" },
  { path: "profile.sector", namespace: "profile", field: "sector", label: "Sector", type: "string" },
  { path: "profile.industry", namespace: "profile", field: "industry", label: "Industry", type: "string" },
  { path: "profile.employees", namespace: "profile", field: "employees", label: "Employees", type: "number" },
  { path: "profile.market_cap", namespace: "profile", field: "market_cap", label: "Market cap", type: "number" },
  { path: "profile.shares_outstanding", namespace: "profile", field: "shares_outstanding", label: "Shares outstanding", type: "number" },
  { path: "profile.exchange", namespace: "profile", field: "exchange", label: "Exchange (profile)", type: "string" },
  { path: "profile.currency", namespace: "profile", field: "currency", label: "Currency (profile)", type: "string" },
  // ratios.*
  { path: "ratios.pe", namespace: "ratios", field: "pe", label: "P/E", type: "number" },
  { path: "ratios.forward_pe", namespace: "ratios", field: "forward_pe", label: "Forward P/E", type: "number" },
  { path: "ratios.pb", namespace: "ratios", field: "pb", label: "Price / book", type: "number" },
  { path: "ratios.ps", namespace: "ratios", field: "ps", label: "Price / sales", type: "number" },
  { path: "ratios.peg", namespace: "ratios", field: "peg", label: "PEG", type: "number" },
  { path: "ratios.ev_ebitda", namespace: "ratios", field: "ev_ebitda", label: "EV / EBITDA", type: "number" },
  { path: "ratios.roe", namespace: "ratios", field: "roe", label: "ROE", type: "number" },
  { path: "ratios.roa", namespace: "ratios", field: "roa", label: "ROA", type: "number" },
  { path: "ratios.roic", namespace: "ratios", field: "roic", label: "ROIC", type: "number" },
  { path: "ratios.gross_margin", namespace: "ratios", field: "gross_margin", label: "Gross margin", type: "number" },
  { path: "ratios.operating_margin", namespace: "ratios", field: "operating_margin", label: "Operating margin", type: "number" },
  { path: "ratios.net_margin", namespace: "ratios", field: "net_margin", label: "Net margin", type: "number" },
  { path: "ratios.current_ratio", namespace: "ratios", field: "current_ratio", label: "Current ratio", type: "number" },
  { path: "ratios.quick_ratio", namespace: "ratios", field: "quick_ratio", label: "Quick ratio", type: "number" },
  { path: "ratios.debt_equity", namespace: "ratios", field: "debt_equity", label: "Debt / equity", type: "number" },
  { path: "ratios.interest_coverage", namespace: "ratios", field: "interest_coverage", label: "Interest coverage", type: "number" },
  { path: "ratios.cash_ratio", namespace: "ratios", field: "cash_ratio", label: "Cash ratio", type: "number" },
  { path: "ratios.free_cash_flow", namespace: "ratios", field: "free_cash_flow", label: "Free cash flow", type: "number" },
  // fundamentals.*
  { path: "fundamentals.revenue", namespace: "fundamentals", field: "revenue", label: "Revenue", type: "number" },
  { path: "fundamentals.gross_profit", namespace: "fundamentals", field: "gross_profit", label: "Gross profit", type: "number" },
  { path: "fundamentals.operating_income", namespace: "fundamentals", field: "operating_income", label: "Operating income", type: "number" },
  { path: "fundamentals.net_income", namespace: "fundamentals", field: "net_income", label: "Net income", type: "number" },
  { path: "fundamentals.ebitda", namespace: "fundamentals", field: "ebitda", label: "EBITDA", type: "number" },
  { path: "fundamentals.eps", namespace: "fundamentals", field: "eps", label: "EPS", type: "number" },
  { path: "fundamentals.book_value", namespace: "fundamentals", field: "book_value", label: "Book value", type: "number" },
  { path: "fundamentals.cash", namespace: "fundamentals", field: "cash", label: "Cash", type: "number" },
  { path: "fundamentals.debt", namespace: "fundamentals", field: "debt", label: "Debt", type: "number" },
  { path: "fundamentals.assets", namespace: "fundamentals", field: "assets", label: "Assets", type: "number" },
  { path: "fundamentals.liabilities", namespace: "fundamentals", field: "liabilities", label: "Liabilities", type: "number" },
  { path: "fundamentals.equity", namespace: "fundamentals", field: "equity", label: "Equity", type: "number" },
  { path: "fundamentals.cash_flow", namespace: "fundamentals", field: "cash_flow", label: "Cash flow", type: "number" },
];

export function signalableFieldDef(path: string): SignalableFieldDef | undefined {
  return SIGNALABLE_FIELDS.find((def) => def.path === path);
}

export function signalableFieldLabel(path: string): string {
  return signalableFieldDef(path)?.label ?? path;
}
