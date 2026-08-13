/**
 * Mirrors `app.agents.company_research.models` and
 * `app.api.v1.research.schemas` field-for-field (verified against the
 * actual backend source, Frontend Milestone 4). Company Research is
 * entirely non-persisted — `CompanyResearchReport` has no `id` of its
 * own; `request_id` only exists on the HTTP-layer envelope, freshly
 * generated per `POST`, and is only ever valid against the same
 * backend process that issued it (in-memory result store, lost on
 * restart — see `docs/architecture/INTELLIGENCE_API.md` §2).
 *
 * There is deliberately no single `sector`/`country`/`market_cap` field
 * on the company profile — those only exist as weighted lists
 * (`sector_analysis`, `country_exposure`) derived from evidence
 * mentions, not a canonical "this company's sector" fact the backend
 * asserts. Do not invent one on the frontend.
 */

export interface CompanyResearchRequest {
  company_name: string;
  ticker?: string | null;
  include_relationships?: boolean;
  include_evidence?: boolean;
}

export interface CompanyOverview {
  company_name: string;
  ticker: string | null;
  matched: boolean;
  entity_recognized: boolean;
  mention_count: number;
  supporting_record_ids: string[];
}

export interface NewsReference {
  record_id: string;
  title: string | null;
  url: string | null;
  published_at: string | null;
  source: string | null;
}

export interface MarketIntelligenceSummary {
  mention_count: number;
  group_confidence: number | null;
  supporting_record_ids: string[];
}

export interface RelationshipReference {
  related_id: string;
  related_label: string;
  relationship_type: string;
  weight: number;
}

export interface SectorExposure {
  sector: string;
  weight: number;
}

export interface CountryExposure {
  country: string;
  weight: number;
}

export interface ThemeExposure {
  keyword: string;
  occurrence_count: number;
}

export interface EvidenceReference {
  record_id: string;
  source: string | null;
  provider: string | null;
  url: string | null;
  published_at: string | null;
  title: string | null;
}

export interface ConfidenceSummary {
  overall_confidence: number;
  supporting_record_count: number;
  basis: string;
}

/** Data-quality flags about the research itself — never market/investment risk. */
export interface RiskFlag {
  code: string;
  description: string;
}

/** `null` means no LLM call was made (the company was never matched) —
 * not a failure state, and must be rendered as "no narrative available",
 * never as an error. */
export interface CompanyResearchNarrative {
  summary: string;
  key_findings: string[];
  risk_commentary: string | null;
}

export interface CompanyResearchReport {
  request: CompanyResearchRequest;
  generated_at: string;
  company_overview: CompanyOverview;
  latest_news: NewsReference[];
  market_intelligence: MarketIntelligenceSummary;
  relationship_analysis: RelationshipReference[];
  sector_analysis: SectorExposure[];
  country_exposure: CountryExposure[];
  theme_analysis: ThemeExposure[];
  supporting_evidence: EvidenceReference[];
  confidence_summary: ConfidenceSummary;
  key_risks: RiskFlag[];
  narrative: CompanyResearchNarrative | null;
}

/** `request_id` is the HTTP-layer id — key every UI reference (routing,
 * comparison, session-recent list) off this, never off anything inside
 * `report` itself. */
export interface CompanyResearchReportEnvelope {
  request_id: string;
  report: CompanyResearchReport;
}

export interface BatchCompanyResearchRequest {
  companies: CompanyResearchRequest[];
}
