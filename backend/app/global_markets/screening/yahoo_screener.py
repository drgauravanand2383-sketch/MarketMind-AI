"""YahooScreenerProvider — discovers INDIA_PENNY_STOCK/US_PENNY_STOCK/
CHINA_PENNY_STOCK candidates via Yahoo Finance's unofficial, undocumented
equity screener endpoint (`POST /v1/finance/screener`), live-verified
during implementation. Reuses the same vendor `YahooFinanceProvider`
already depends on for quotes/history — no new vendor trust boundary is
introduced by this module, though the screener endpoint specifically
(unlike the public chart endpoint) requires a session cookie + CSRF
"crumb" obtained via an unauthenticated bootstrap flow
(`GET /v1/test/getcrumb`), also live-verified.

**Data-quality caveat, handled explicitly below**: the screener's own
`quoteType=EQUITY` query filter does not reliably exclude every non-
common-equity instrument — mutual funds and ETFs were observed live
returning `quoteType: "EQUITY"` despite not being one. `_looks_like_a_fund_or_derivative`
is a documented, best-effort name-substring heuristic, not a guarantee
— the real, authoritative filter remains the downstream
`ConfigurableEligibilityProvider` gate every candidate still passes
through once its real quote is fetched.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.global_markets.eligibility.models import PennyStockEligibilityCriteria
from app.global_markets.models import ReportCategory
from app.global_markets.screening.provider import PennyStockScreeningProvider
from app.global_markets.universe.models import UniverseEntry
from app.providers.exceptions import (
    ProviderConnectionError,
    ProviderResponseError,
    ProviderTimeoutError,
)

__all__ = ["YahooScreenerProvider", "YahooScreenerConfig"]

_logger = logging.getLogger("marketmind.global_markets.screening.yahoo")
PROVIDER_ID = "yahoo_screener"

_REGION_FOR_CATEGORY: dict[ReportCategory, str] = {
    ReportCategory.INDIA_PENNY_STOCK: "in",
    ReportCategory.US_PENNY_STOCK: "us",
    ReportCategory.CHINA_PENNY_STOCK: "cn",
}

# A pragmatic, documented heuristic (see module docstring) — not
# exhaustive, not authoritative. Matched against the candidate's own
# lowercased display name.
_NON_COMMON_EQUITY_NAME_SUBSTRINGS: tuple[str, ...] = (
    "fund", "etf", "trust", "warrant", " right", "rights", " unit",
    "spac", "acquisition corp", "depositary", "notes due", " index",
)


class YahooScreenerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://query1.finance.yahoo.com"
    # Bootstraps the session cookie the crumb (and the screener call
    # itself) both depend on. Live-verified to return HTTP 404 while
    # still setting a usable `Set-Cookie` header — the 404 itself is
    # expected and not treated as a failure.
    cookie_bootstrap_url: str = "https://fc.yahoo.com"
    crumb_url: str = "https://query1.finance.yahoo.com/v1/test/getcrumb"
    timeout: float = Field(default=10.0, gt=0)
    user_agent: str = "MarketMind-AI/1.0"
    # How many raw candidates to request per query — deliberately larger
    # than `limit` so client-side fund/ETF/warrant filtering still leaves
    # room to fill `limit` genuine equities from a single request.
    fetch_size_multiplier: int = Field(default=4, ge=1)
    max_fetch_size: int = Field(default=250, ge=1)


class YahooScreenerProvider(PennyStockScreeningProvider):
    """Discovers equity penny-stock candidates from Yahoo Finance's
    unofficial screener endpoint, one `MarketRegion` per call."""

    def __init__(
        self,
        config: YahooScreenerConfig,
        *,
        client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self._config = config
        self._client_factory = client_factory
        # Cached across calls (crumbs are session-lived, not single-use)
        # — refreshed once, automatically, on a 401 "Invalid Crumb"
        # response rather than re-fetched on every `discover()` call.
        self._cached_crumb: str | None = None

    async def discover(
        self, category: ReportCategory, criteria: PennyStockEligibilityCriteria, limit: int
    ) -> tuple[UniverseEntry, ...]:
        region = _REGION_FOR_CATEGORY.get(category)
        if region is None:
            return ()

        fetch_size = min(limit * self._config.fetch_size_multiplier, self._config.max_fetch_size)
        body = {
            "size": fetch_size,
            "offset": 0,
            "sortField": "intradaymarketcap",
            "sortType": "DESC",
            "quoteType": "EQUITY",
            "query": {"operator": "and", "operands": self._query_operands(region, criteria)},
        }

        async with self._client_factory(timeout=self._config.timeout) as client:
            payload = await self._post_screener(client, region, body)

        entries: list[UniverseEntry] = []
        seen: set[str] = set()
        for quote in self._extract_quotes(payload):
            entry = self._entry_from_quote(quote)
            if entry is None or entry.ticker in seen:
                continue
            seen.add(entry.ticker)
            entries.append(entry)
            if len(entries) >= limit:
                break
        return tuple(entries)

    def _query_operands(self, region: str, criteria: PennyStockEligibilityCriteria) -> list[dict[str, object]]:
        operands: list[dict[str, object]] = [{"operator": "EQ", "operands": ["region", region]}]
        if criteria.max_price is not None:
            operands.append({"operator": "lt", "operands": ["intradayprice", criteria.max_price]})
        if criteria.min_market_cap is not None:
            operands.append({"operator": "gt", "operands": ["intradaymarketcap", criteria.min_market_cap]})
        if criteria.max_market_cap is not None:
            operands.append({"operator": "lt", "operands": ["intradaymarketcap", criteria.max_market_cap]})
        return operands

    async def _post_screener(self, client: httpx.AsyncClient, region: str, body: dict[str, object]) -> dict[str, Any]:
        crumb = await self._get_crumb(client)
        response = await self._do_post(client, region, crumb, body)
        if response.status_code == 401:
            # A cached crumb can expire independently of its cookie —
            # refresh exactly once and retry, never loop indefinitely.
            self._cached_crumb = None
            crumb = await self._get_crumb(client)
            response = await self._do_post(client, region, crumb, body)

        if response.status_code != 200:
            message = f"Yahoo screener returned HTTP {response.status_code} for region {region!r}."
            raise ProviderResponseError(message, provider_id=PROVIDER_ID)
        try:
            payload = response.json()
        except ValueError as exc:
            message = f"Yahoo screener response for region {region!r} was not valid JSON: {exc}"
            raise ProviderResponseError(message, provider_id=PROVIDER_ID) from exc
        if not isinstance(payload, dict):
            message = f"Yahoo screener response for region {region!r} was not a JSON object."
            raise ProviderResponseError(message, provider_id=PROVIDER_ID)
        return payload

    async def _get_crumb(self, client: httpx.AsyncClient) -> str:
        if self._cached_crumb is not None:
            return self._cached_crumb
        headers = {"User-Agent": self._config.user_agent}
        try:
            # Sets the session cookie the crumb call below depends on —
            # its own response body/status is never inspected (see this
            # config field's own docstring on the expected 404).
            await client.get(self._config.cookie_bootstrap_url, headers=headers)
            crumb_response = await client.get(self._config.crumb_url, headers=headers)
        except httpx.TimeoutException as exc:
            message = f"Yahoo screener session bootstrap timed out: {exc}"
            raise ProviderTimeoutError(message, provider_id=PROVIDER_ID) from exc
        except httpx.HTTPError as exc:
            message = f"Yahoo screener session bootstrap failed: {exc}"
            raise ProviderConnectionError(message, provider_id=PROVIDER_ID) from exc

        if crumb_response.status_code != 200 or not crumb_response.text.strip():
            message = f"Yahoo Finance did not return a usable crumb (HTTP {crumb_response.status_code})."
            raise ProviderResponseError(message, provider_id=PROVIDER_ID)
        self._cached_crumb = crumb_response.text.strip()
        return self._cached_crumb

    async def _do_post(
        self, client: httpx.AsyncClient, region: str, crumb: str, body: dict[str, object]
    ) -> httpx.Response:
        params = {
            "crumb": crumb, "lang": "en-US", "region": region.upper(),
            "formatted": "false", "corsDomain": "finance.yahoo.com",
        }
        headers = {"User-Agent": self._config.user_agent, "Content-Type": "application/json"}
        try:
            return await client.post(
                f"{self._config.base_url}/v1/finance/screener", params=params, json=body, headers=headers
            )
        except httpx.TimeoutException as exc:
            message = f"Yahoo screener request for region {region!r} timed out: {exc}"
            raise ProviderTimeoutError(message, provider_id=PROVIDER_ID) from exc
        except httpx.HTTPError as exc:
            message = f"Yahoo screener request for region {region!r} failed: {exc}"
            raise ProviderConnectionError(message, provider_id=PROVIDER_ID) from exc

    def _extract_quotes(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        finance = payload.get("finance") if isinstance(payload, dict) else None
        result = finance.get("result") if isinstance(finance, dict) else None
        if not result or not isinstance(result, list) or not isinstance(result[0], dict):
            return []
        quotes = result[0].get("quotes")
        return quotes if isinstance(quotes, list) else []

    def _entry_from_quote(self, quote: dict[str, Any]) -> UniverseEntry | None:
        if quote.get("quoteType") != "EQUITY":
            return None
        symbol = quote.get("symbol")
        name = quote.get("longName") or quote.get("shortName")
        if not symbol or not name:
            return None
        if any(term in name.lower() for term in _NON_COMMON_EQUITY_NAME_SUBSTRINGS):
            return None
        try:
            return UniverseEntry(ticker=symbol, name=name)
        except ValidationError:
            return None
