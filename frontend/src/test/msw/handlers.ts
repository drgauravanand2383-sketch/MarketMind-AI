import { http, HttpResponse } from "msw";
import { API_BASE_URL } from "@/services/api/config";
import {
  buildAuthenticationResponse,
  buildInitialAnalysisState,
  buildMeta,
  buildResearchReport,
  testApplicationHealth,
  testPortfolioIntelligenceReport,
  testReadiness,
  testRecommendationResult,
  testRiskAssessment,
  testVersion,
  testWatchlistStatistics,
  wrapSuccess,
} from "@/test/msw/fixtures";
import { createResultStore } from "@/test/msw/result-store";
import { evaluateCompany } from "@/test/msw/screening-evaluator";
import {
  createScreeningProfile,
  deleteScreeningProfile,
  duplicateScreeningProfile,
  getScreeningProfile,
  nameTaken,
  queryScreeningProfiles,
  updateScreeningProfile,
  type ScreeningProfileQuery,
} from "@/test/msw/screening-store";
import {
  addCompany,
  createWatchlist,
  deleteWatchlist,
  getWatchlist,
  hasTicker,
  queryWatchlists,
  removeCompany,
  renameWatchlist,
  updateNotes,
  type WatchlistQuery,
} from "@/test/msw/watchlist-store";
import { evaluateAlerts, evaluateSignalDefinition, evaluateStrategies } from "@/test/msw/decision-center-evaluator";
import { getSignalDefinition, getStrategy, listAlerts, listEnabledAlertRules, listSignalDefinitions, listStrategies, nextAlertIdValue, appendAlerts } from "@/test/msw/decision-center-store";
import { createBacktest, getBacktestResult, getBacktestRun } from "@/test/msw/backtesting-store";
import { generateExplanation, getExplainabilityResult } from "@/test/msw/explainability-store";
import { getLatestRun, getRankedAssets, getReport, getRun, listRuns } from "@/test/msw/global-markets-store";
import type { ReportCategory } from "@/types/global-markets";
import type { AddCompanyRequest, CreateWatchlistRequest, RenameWatchlistRequest, UpdateNotesRequest, WatchlistItem } from "@/types/watchlist";
import type { BatchCompanyResearchRequest, CompanyResearchReport, CompanyResearchReportEnvelope, CompanyResearchRequest } from "@/types/research";
import type {
  CreateScreeningProfileRequest,
  DuplicateScreeningProfileRequest,
  RunScreeningRequest,
  ScreeningRunEnvelope,
  UpdateScreeningProfileRequest,
} from "@/types/screening";
import type { EvaluateAlertsRequest } from "@/types/alerts";
import type { EvaluateSignalsRequest, SignalEvaluationEnvelope } from "@/types/signals";
import type { EvaluateStrategyRequest } from "@/types/strategy";
import type { GenerateRecommendationsRequest, RecommendationCandidate, RecommendationSummary } from "@/types/portfolio";
import type { CreateBacktestRequest } from "@/types/backtesting";
import type { GenerateExplanationRequest } from "@/types/explainability";

export const researchReportStore = createResultStore<CompanyResearchReport>("test-research");
export const screeningResultStore = createResultStore<readonly [string, ScreeningRunEnvelope["results"]]>("test-screen-result");
export const signalResultStore = createResultStore<SignalEvaluationEnvelope["batch_result"]>("test-signal-result");
// Keyed by the evaluation's own `request_id`, not a separately-generated
// cache id — mirrors the real backend's own convention ("`result_id` is
// the evaluation request's id", `app/api/v1/strategies/router.py`).
const strategyResultsByRequestId = new Map<string, ReturnType<typeof evaluateStrategies>>();

function notFound() {
  return HttpResponse.json({ error: "not_found", message: "Not found.", meta: buildMeta() }, { status: 404 });
}

function parseListQuery(url: URL): WatchlistQuery {
  const sortParam = url.searchParams.get("sort");
  const sort = sortParam === "name" || sortParam === "created_at" || sortParam === "updated_at" ? sortParam : "updated_at";
  const directionParam = url.searchParams.get("direction");
  const direction = directionParam === "desc" ? "desc" : "asc";
  return {
    page: Number(url.searchParams.get("page") ?? "1"),
    page_size: Number(url.searchParams.get("page_size") ?? "20"),
    sort,
    direction,
    ...(url.searchParams.get("name") && { name: url.searchParams.get("name") ?? undefined }),
    ...(url.searchParams.get("sector") && { sector: url.searchParams.get("sector") ?? undefined }),
    ...(url.searchParams.get("country") && { country: url.searchParams.get("country") ?? undefined }),
    ...(url.searchParams.get("theme") && { theme: url.searchParams.get("theme") ?? undefined }),
    ...(url.searchParams.get("ticker") && { ticker: url.searchParams.get("ticker") ?? undefined }),
  };
}

function watchlistListHandler(path: string) {
  return http.get(`${API_BASE_URL}${path}`, ({ request }) => {
    const url = new URL(request.url);
    const query = parseListQuery(url);
    const { data, total } = queryWatchlists(query);
    return HttpResponse.json({ data, total, page: query.page, page_size: query.page_size, meta: buildMeta() });
  });
}

export const handlers = [
  http.post(`${API_BASE_URL}/auth/login`, () => HttpResponse.json(wrapSuccess(buildAuthenticationResponse()), { status: 201 })),
  http.post(`${API_BASE_URL}/auth/refresh`, () => HttpResponse.json(wrapSuccess(buildAuthenticationResponse()), { status: 201 })),
  http.post(`${API_BASE_URL}/auth/logout`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API_BASE_URL}/health`, () => HttpResponse.json(wrapSuccess(testApplicationHealth))),
  http.get(`${API_BASE_URL}/ready`, () => HttpResponse.json(wrapSuccess(testReadiness))),
  http.get(`${API_BASE_URL}/version`, () => HttpResponse.json(wrapSuccess(testVersion))),

  watchlistListHandler("/watchlists"),
  watchlistListHandler("/portfolio"),

  http.post(`${API_BASE_URL}/watchlists`, async ({ request }) => {
    const body = (await request.json()) as CreateWatchlistRequest;
    const watchlist = createWatchlist(body.name, body.description ?? "");
    return HttpResponse.json(wrapSuccess(watchlist), { status: 201 });
  }),

  http.get(`${API_BASE_URL}/watchlists/:id`, ({ params }) => {
    const watchlist = getWatchlist(String(params.id));
    if (!watchlist) return notFound();
    return HttpResponse.json(wrapSuccess(watchlist));
  }),

  // These four literal paths must be registered before `/portfolio/:id`
  // below — MSW (like the real FastAPI router it mirrors, see
  // `docs/release/API_CONTRACT_V1.md` §1) matches handlers in
  // registration order, and `:id` would otherwise swallow "summary" /
  // "intelligence" / "risk" / "recommendations" as if each were a
  // portfolio id, shadowing every one of these handlers.
  http.get(`${API_BASE_URL}/portfolio/summary`, () => HttpResponse.json(wrapSuccess(testWatchlistStatistics))),
  http.get(`${API_BASE_URL}/portfolio/intelligence`, () => HttpResponse.json(wrapSuccess(testPortfolioIntelligenceReport))),
  http.get(`${API_BASE_URL}/portfolio/risk`, () => HttpResponse.json(wrapSuccess(testRiskAssessment))),
  http.get(`${API_BASE_URL}/portfolio/recommendations`, () => HttpResponse.json(wrapSuccess(testRecommendationResult))),

  http.post(`${API_BASE_URL}/portfolio/recommendations`, async ({ request }) => {
    const body = (await request.json()) as GenerateRecommendationsRequest;
    const candidates: RecommendationCandidate[] = (body.evidence ?? []).map((evidence) => ({
      ticker: evidence.ticker,
      company_name: evidence.company_name ?? null,
      country: evidence.country ?? null,
      sector: evidence.sector ?? null,
      industry: evidence.industry ?? null,
      overall_score: 70,
      confidence: 65,
      recommendation: "WATCH",
      reasoning: "Generated from minimal identity evidence.",
      supporting_signals: evidence.signals ?? [],
      supporting_alerts: evidence.alerts ?? [],
      screening_score: null,
      planning_score: evidence.planning_score ?? null,
      research_score: null,
      portfolio_score: null,
      signal_score: null,
      alert_score: null,
      created_at: new Date().toISOString(),
    }));
    const summary: RecommendationSummary = {
      strong_buy: 0,
      buy: 0,
      watch: candidates.length,
      hold: 0,
      avoid: 0,
      average_score: candidates.length === 0 ? 0 : 70,
      average_confidence: candidates.length === 0 ? 0 : 65,
    };
    return HttpResponse.json(
      wrapSuccess({ request_id: `test-rec-${Date.now().toString()}`, generated_at: new Date().toISOString(), total_candidates: candidates.length, recommendations: candidates, summary }),
      { status: 201 },
    );
  }),

  // v1.2 Priority 8. Defaults to UNAVAILABLE (matches `testInitialAnalysisState`)
  // — individual tests override with `server.use(...)` for ANALYZING/READY/
  // PARTIAL/ERROR scenarios, the same pattern every other handler here uses.
  http.get(`${API_BASE_URL}/portfolio/:id/analysis-status`, ({ params }) =>
    HttpResponse.json(wrapSuccess(buildInitialAnalysisState({ portfolio_id: String(params.id) }))),
  ),
  http.post(`${API_BASE_URL}/portfolio/:id/analysis`, ({ params }) =>
    HttpResponse.json(wrapSuccess(buildInitialAnalysisState({ portfolio_id: String(params.id) })), { status: 202 }),
  ),

  http.get(`${API_BASE_URL}/portfolio/:id`, ({ params }) => {
    const watchlist = getWatchlist(String(params.id));
    if (!watchlist) return notFound();
    return HttpResponse.json(wrapSuccess(watchlist));
  }),

  http.patch(`${API_BASE_URL}/watchlists/:id`, async ({ params, request }) => {
    const body = (await request.json()) as RenameWatchlistRequest;
    const watchlist = renameWatchlist(String(params.id), body.name);
    if (!watchlist) return notFound();
    return HttpResponse.json(wrapSuccess(watchlist));
  }),

  http.delete(`${API_BASE_URL}/watchlists/:id`, ({ params }) => {
    const deleted = deleteWatchlist(String(params.id));
    if (!deleted) return notFound();
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API_BASE_URL}/watchlists/:id/companies`, async ({ params, request }) => {
    const id = String(params.id);
    const body = (await request.json()) as AddCompanyRequest;
    if (!getWatchlist(id)) return notFound();
    if (hasTicker(id, body.ticker)) {
      return HttpResponse.json({ error: "conflict", message: "Ticker already tracked.", meta: buildMeta() }, { status: 409 });
    }
    const item: WatchlistItem = {
      ticker: body.ticker,
      company_name: body.company_name ?? null,
      country: body.country ?? null,
      sector: body.sector ?? null,
      theme: body.theme ?? null,
      source_agent: body.source_agent ?? null,
      confidence: body.confidence ?? null,
      reason: body.reason ?? null,
      notes: body.notes ?? null,
      added_at: new Date().toISOString(),
    };
    const watchlist = addCompany(id, item);
    return HttpResponse.json(wrapSuccess(watchlist), { status: 201 });
  }),

  http.delete(`${API_BASE_URL}/watchlists/:id/companies/:ticker`, ({ params }) => {
    const watchlist = removeCompany(String(params.id), String(params.ticker));
    if (!watchlist) return notFound();
    return HttpResponse.json(wrapSuccess(watchlist));
  }),

  http.patch(`${API_BASE_URL}/watchlists/:id/companies/:ticker/notes`, async ({ params, request }) => {
    const body = (await request.json()) as UpdateNotesRequest;
    const watchlist = updateNotes(String(params.id), String(params.ticker), body.notes);
    if (!watchlist) return notFound();
    return HttpResponse.json(wrapSuccess(watchlist));
  }),

  http.get(`${API_BASE_URL}/watchlists/:id/snapshot`, ({ params }) => {
    const watchlist = getWatchlist(String(params.id));
    if (!watchlist) return notFound();
    const confidences = watchlist.items.map((item) => item.confidence).filter((value): value is number => value !== null);
    const average = confidences.length > 0 ? confidences.reduce((sum, value) => sum + value, 0) / confidences.length : null;
    return HttpResponse.json(
      wrapSuccess({
        watchlist_id: watchlist.id,
        snapshot_time: new Date().toISOString(),
        total_companies: watchlist.items.length,
        average_confidence: average,
        summary: `${String(watchlist.items.length)} companies tracked.`,
      }),
    );
  }),

  // Company Research — literal paths registered before `/research/:id`,
  // same reasoning as `/portfolio/summary` etc. above.
  http.post(`${API_BASE_URL}/research/company`, async ({ request }) => {
    const body = (await request.json()) as CompanyResearchRequest;
    const report = buildResearchReport({
      request: body,
      company_overview: {
        company_name: body.company_name,
        ticker: body.ticker ?? null,
        matched: true,
        entity_recognized: true,
        mention_count: 12,
        supporting_record_ids: ["rec-1"],
      },
    });
    const request_id = researchReportStore.put(report);
    return HttpResponse.json(wrapSuccess({ request_id, report } satisfies CompanyResearchReportEnvelope), { status: 201 });
  }),

  http.post(`${API_BASE_URL}/research/batch`, async ({ request }) => {
    const body = (await request.json()) as BatchCompanyResearchRequest;
    const envelopes: CompanyResearchReportEnvelope[] = body.companies.map((companyRequest) => {
      const report = buildResearchReport({
        request: companyRequest,
        company_overview: {
          company_name: companyRequest.company_name,
          ticker: companyRequest.ticker ?? null,
          matched: true,
          entity_recognized: true,
          mention_count: 12,
          supporting_record_ids: ["rec-1"],
        },
      });
      const request_id = researchReportStore.put(report);
      return { request_id, report };
    });
    return HttpResponse.json(wrapSuccess(envelopes), { status: 201 });
  }),

  http.get(`${API_BASE_URL}/research/:requestId`, ({ params }) => {
    const report = researchReportStore.get(String(params.requestId));
    if (!report) return notFound();
    return HttpResponse.json(wrapSuccess({ request_id: String(params.requestId), report } satisfies CompanyResearchReportEnvelope));
  }),

  // Screening — literal paths (`/profiles/:id/duplicate`, `/run`,
  // `/results/:id`) registered before the bare `/profiles/:id` — same
  // registration-order requirement as the watchlist/portfolio handlers
  // above.
  http.get(`${API_BASE_URL}/screening/profiles`, ({ request }) => {
    const url = new URL(request.url);
    const sortParam = url.searchParams.get("sort");
    const sort = sortParam === "name" || sortParam === "created_at" ? sortParam : "updated_at";
    const query: ScreeningProfileQuery = {
      page: Number(url.searchParams.get("page") ?? "1"),
      page_size: Number(url.searchParams.get("page_size") ?? "20"),
      sort,
      direction: url.searchParams.get("direction") === "desc" ? "desc" : "asc",
      ...(url.searchParams.get("name") && { name: url.searchParams.get("name") ?? undefined }),
    };
    const { data, total } = queryScreeningProfiles(query);
    return HttpResponse.json({ data, total, page: query.page, page_size: query.page_size, meta: buildMeta() });
  }),

  http.post(`${API_BASE_URL}/screening/profiles`, async ({ request }) => {
    const body = (await request.json()) as CreateScreeningProfileRequest;
    if (nameTaken(body.name)) {
      return HttpResponse.json({ error: "conflict", message: "Name already in use.", meta: buildMeta() }, { status: 409 });
    }
    const profile = createScreeningProfile(body.name, body.description ?? "", body.filters ?? [], body.groups ?? []);
    return HttpResponse.json(wrapSuccess(profile), { status: 201 });
  }),

  http.post(`${API_BASE_URL}/screening/profiles/:id/duplicate`, async ({ params, request }) => {
    const body = (await request.json()) as DuplicateScreeningProfileRequest;
    const result = duplicateScreeningProfile(String(params.id), body.new_name);
    if (result === "not_found") return notFound();
    if (result === "conflict") {
      return HttpResponse.json({ error: "conflict", message: "Name already in use.", meta: buildMeta() }, { status: 409 });
    }
    return HttpResponse.json(wrapSuccess(result), { status: 201 });
  }),

  http.post(`${API_BASE_URL}/screening/run`, async ({ request }) => {
    const body = (await request.json()) as RunScreeningRequest;
    const profile = getScreeningProfile(body.profile_id);
    if (!profile) return notFound();
    const results = body.companies.map((company) => evaluateCompany(profile, company));
    const result_id = screeningResultStore.put([body.profile_id, results] as const);
    return HttpResponse.json(wrapSuccess({ result_id, profile_id: body.profile_id, results } satisfies ScreeningRunEnvelope), {
      status: 201,
    });
  }),

  http.get(`${API_BASE_URL}/screening/results/:id`, ({ params }) => {
    const cached = screeningResultStore.get(String(params.id));
    if (!cached) return notFound();
    const [profile_id, results] = cached;
    return HttpResponse.json(wrapSuccess({ result_id: String(params.id), profile_id, results } satisfies ScreeningRunEnvelope));
  }),

  http.patch(`${API_BASE_URL}/screening/profiles/:id`, async ({ params, request }) => {
    const body = (await request.json()) as UpdateScreeningProfileRequest;
    const profile = updateScreeningProfile(String(params.id), {
      ...(body.name !== undefined && { name: body.name }),
      ...(body.description !== undefined && body.description !== null && { description: body.description }),
      ...(body.is_default !== undefined && { is_default: body.is_default }),
      ...(body.filters !== undefined && { filters: body.filters }),
      ...(body.groups !== undefined && { groups: body.groups }),
    });
    if (!profile) return notFound();
    return HttpResponse.json(wrapSuccess(profile));
  }),

  http.delete(`${API_BASE_URL}/screening/profiles/:id`, ({ params }) => {
    const deleted = deleteScreeningProfile(String(params.id));
    if (!deleted) return notFound();
    return new HttpResponse(null, { status: 204 });
  }),

  http.get(`${API_BASE_URL}/screening/profiles/:id`, ({ params }) => {
    const profile = getScreeningProfile(String(params.id));
    if (!profile) return notFound();
    return HttpResponse.json(wrapSuccess(profile));
  }),

  // Strategy Evaluation — literal paths (`/evaluate`, `/results/:id`)
  // registered before the bare `/:strategyId` this frontend never calls,
  // same registration-order convention as above.
  http.get(`${API_BASE_URL}/strategies`, ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get("page") ?? "1");
    const page_size = Number(url.searchParams.get("page_size") ?? "20");
    const data = listStrategies();
    return HttpResponse.json({ data, total: data.length, page, page_size, meta: buildMeta() });
  }),

  // Simplification: always evaluates against `testRecommendationResult`'s
  // fixed candidates rather than tracking a real recommendation-result
  // store keyed by `recommendation_result_id` — sufficient for testing
  // the Strategy tab's own UI/wiring, not a reimplementation of the real
  // cross-domain lookup.
  http.post(`${API_BASE_URL}/strategies/evaluate`, async ({ request }) => {
    const body = (await request.json()) as EvaluateStrategyRequest;
    const strategies = body.strategy_ids && body.strategy_ids.length > 0 ? body.strategy_ids.map((id) => getStrategy(id)).filter((s): s is NonNullable<typeof s> => Boolean(s)) : listStrategies();
    const candidates = testRecommendationResult.recommendations;
    const result = evaluateStrategies(`test-strategy-eval-${crypto.randomUUID()}`, candidates, strategies);
    strategyResultsByRequestId.set(result.request_id, result);
    return HttpResponse.json(wrapSuccess(result), { status: 201 });
  }),

  http.get(`${API_BASE_URL}/strategies/results/:id`, ({ params }) => {
    const result = strategyResultsByRequestId.get(String(params.id));
    if (!result) return notFound();
    return HttpResponse.json(wrapSuccess(result));
  }),

  // Signal Detection — literal paths registered before any bare `:id`.
  http.get(`${API_BASE_URL}/signals/definitions`, ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get("page") ?? "1");
    const page_size = Number(url.searchParams.get("page_size") ?? "20");
    const data = listSignalDefinitions();
    return HttpResponse.json({ data, total: data.length, page, page_size, meta: buildMeta() });
  }),

  http.post(`${API_BASE_URL}/signals/evaluate`, async ({ request }) => {
    const body = (await request.json()) as EvaluateSignalsRequest;
    const definition = getSignalDefinition(body.definition_id);
    if (!definition) return notFound();
    const signals = body.snapshots.map((snapshot) => evaluateSignalDefinition(definition, snapshot));
    const triggered = signals.filter((s) => s.triggered).length;
    const batch_result = {
      signals,
      evaluated: signals.length,
      triggered,
      average_score: signals.length === 0 ? 0 : signals.reduce((sum, s) => sum + s.score, 0) / signals.length,
      summary: `${String(triggered)} of ${String(signals.length)} companies triggered "${definition.name}".`,
    };
    const result_id = signalResultStore.put(batch_result);
    return HttpResponse.json(wrapSuccess({ result_id, definition_id: definition.id, batch_result } satisfies SignalEvaluationEnvelope), {
      status: 201,
    });
  }),

  http.get(`${API_BASE_URL}/signals/results/:id`, ({ params }) => {
    const batch_result = signalResultStore.get(String(params.id));
    if (!batch_result) return notFound();
    return HttpResponse.json(wrapSuccess({ result_id: String(params.id), definition_id: "", batch_result } satisfies SignalEvaluationEnvelope));
  }),

  // Alerts — literal `/evaluate` registered before the bare `/:alertId`.
  http.get(`${API_BASE_URL}/alerts`, ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get("page") ?? "1");
    const page_size = Number(url.searchParams.get("page_size") ?? "20");
    const sort = url.searchParams.get("sort");
    const direction = url.searchParams.get("direction") === "desc" ? -1 : 1;
    let data = listAlerts();
    if (sort === "priority" || sort === "status" || sort === "ticker" || sort === "created_at") {
      data = [...data].sort((a, b) => {
        const left = a[sort];
        const right = b[sort];
        return left < right ? -direction : left > right ? direction : 0;
      });
    }
    const start = (page - 1) * page_size;
    return HttpResponse.json({ data: data.slice(start, start + page_size), total: data.length, page, page_size, meta: buildMeta() });
  }),

  http.post(`${API_BASE_URL}/alerts/evaluate`, async ({ request }) => {
    const body = (await request.json()) as EvaluateAlertsRequest;
    const generated = evaluateAlerts(body.signals, listEnabledAlertRules(), nextAlertIdValue);
    appendAlerts(generated);
    return HttpResponse.json(
      wrapSuccess({ alerts: generated, generated: generated.length, suppressed: 0, summary: `${String(generated.length)} alerts generated.` }),
      { status: 201 },
    );
  }),

  http.get(`${API_BASE_URL}/alerts/:id`, ({ params }) => {
    const alert = listAlerts().find((a) => a.id === String(params.id));
    if (!alert) return notFound();
    return HttpResponse.json(wrapSuccess(alert));
  }),

  // Backtesting — literal `/backtests` (create) registered before the
  // bare `/:runId` and its `/results` child, same convention as above.
  http.post(`${API_BASE_URL}/backtests`, async ({ request }) => {
    const body = (await request.json()) as CreateBacktestRequest;
    const result = createBacktest(body);
    return HttpResponse.json(wrapSuccess(result), { status: 201 });
  }),

  http.get(`${API_BASE_URL}/backtests/:runId/results`, ({ params }) => {
    const result = getBacktestResult(String(params.runId));
    if (!result) return notFound();
    return HttpResponse.json(wrapSuccess(result));
  }),

  http.get(`${API_BASE_URL}/backtests/:runId`, ({ params }) => {
    const run = getBacktestRun(String(params.runId));
    if (!run) return notFound();
    return HttpResponse.json(wrapSuccess(run));
  }),

  // Explainability & Performance Attribution.
  http.post(`${API_BASE_URL}/explainability`, async ({ request }) => {
    const body = (await request.json()) as GenerateExplanationRequest;
    const result = generateExplanation(body);
    return HttpResponse.json(wrapSuccess(result), { status: 201 });
  }),

  http.get(`${API_BASE_URL}/explainability/:requestId`, ({ params }) => {
    const result = getExplainabilityResult(String(params.requestId));
    if (!result) return notFound();
    return HttpResponse.json(wrapSuccess(result));
  }),

  // Global Markets — read-only. Literal `/runs/latest` registered before
  // the bare `/runs/:runId`, same registration-order convention as
  // `/portfolio/summary` etc. above (and the real backend router's own
  // `/runs/latest` docstring).
  http.get(`${API_BASE_URL}/global-markets/runs/latest`, () => {
    const run = getLatestRun();
    if (!run) return notFound();
    return HttpResponse.json(wrapSuccess(run));
  }),

  http.get(`${API_BASE_URL}/global-markets/runs`, () => {
    const data = listRuns();
    return HttpResponse.json({ data, total: data.length, page: 1, page_size: data.length || 1, meta: buildMeta() });
  }),

  http.get(`${API_BASE_URL}/global-markets/runs/:runId`, ({ params }) => {
    const run = getRun(String(params.runId));
    if (!run) return notFound();
    return HttpResponse.json(wrapSuccess(run));
  }),

  http.get(`${API_BASE_URL}/global-markets/runs/:runId/categories/:category/ranked-assets`, ({ params }) => {
    const data = getRankedAssets(String(params.runId), params.category as ReportCategory);
    return HttpResponse.json({ data, total: data.length, page: 1, page_size: data.length || 1, meta: buildMeta() });
  }),

  http.get(`${API_BASE_URL}/global-markets/runs/:runId/categories/:category/report`, ({ params }) => {
    const report = getReport(String(params.runId), params.category as ReportCategory);
    if (!report) return notFound();
    return HttpResponse.json(wrapSuccess(report));
  }),
];
