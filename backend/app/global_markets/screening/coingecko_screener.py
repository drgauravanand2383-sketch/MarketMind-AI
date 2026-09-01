"""CoinGeckoScreeningProvider — discovers `LOW_CAP_CRYPTO` candidates via
CoinGecko's public, no-API-key `/coins/markets` endpoint, live-verified
during implementation. Only ever handles `ReportCategory.LOW_CAP_CRYPTO`
— every other category returns `()` immediately.

Never gates on unit token price — a $0.0001 token is not inherently a
"low-cap opportunity" (see `PennyStockEligibilityCriteria`'s own
docstring's explicit "do not rank crypto primarily by token price" rule).
Filtering here is by `market_cap` alone, against the exact same approved
`DEFAULT_ELIGIBILITY_CRITERIA[LOW_CAP_CRYPTO]` band the downstream
eligibility gate also enforces (see `criteria_for_category`).

Pages are requested `order=market_cap_desc`, scanning from the largest
market cap downward and stopping once a page's market caps fall below
`criteria.min_market_cap` (every remaining coin, on this page and every
later one, can only be smaller) — bounded to `_MAX_PAGES` regardless, so
a misconfigured band can never cause an unbounded number of requests.

A `market_cap` of `0`/`null` (data CoinGecko itself could not verify —
observed live for several inactive/illiquid listings) is never treated
as "eligible because it's below the ceiling"; it is excluded outright —
this codebase's "a genuinely missing field is missing data, not evidence
either way" principle, applied at the discovery stage itself.

A discovered coin's ticker is `"{SYMBOL}-USD"`, matching this codebase's
existing crypto ticker convention (`DEFAULT_UNIVERSES[CRYPTO]`, e.g.
`"BTC-USD"`) — the same suffix format `YahooFinanceProvider`'s chart
endpoint expects for the actual downstream quote/history fetch.

**Known limitation**: CoinGecko tracks far more coins than Yahoo
Finance's chart endpoint actually has data for; a discovered low-cap
token Yahoo cannot quote is silently excluded by `CategoryDataPipeline`'s
own existing per-ticker fetch isolation — an honest, expected data-
coverage gap between the two vendors, not a bug. Mitigated (not
eliminated) by `GlobalMarketIntelligenceWorkflow`'s own candidate-
overfetch multiplier requesting more candidates than the category's
`top_n` actually needs.
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
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)

__all__ = ["CoinGeckoScreeningProvider", "CoinGeckoScreenerConfig"]

_logger = logging.getLogger("marketmind.global_markets.screening.coingecko")
PROVIDER_ID = "coingecko_screener"

# A pragmatic, documented heuristic, not an exhaustive or authoritative
# list — excludes fiat-pegged stablecoins that would otherwise trivially
# satisfy a market-cap/liquidity band while being uninteresting (and
# misleading) as a "discovery" candidate.
_STABLECOIN_SYMBOLS: frozenset[str] = frozenset({
    "usdt", "usdc", "dai", "busd", "tusd", "usdp", "gusd", "fdusd", "pyusd",
    "usde", "frax", "usdd", "lusd", "susd", "eurt", "eurs",
})


class CoinGeckoScreenerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.coingecko.com/api/v3"
    timeout: float = Field(default=10.0, gt=0)
    per_page: int = Field(default=250, ge=1, le=250)
    max_pages: int = Field(default=8, ge=1)
    user_agent: str = "MarketMind-AI/1.0"


class CoinGeckoScreeningProvider(PennyStockScreeningProvider):
    """Discovers `LOW_CAP_CRYPTO` candidates from CoinGecko's public
    market-cap-ranked coin list."""

    def __init__(
        self,
        config: CoinGeckoScreenerConfig,
        *,
        client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self._config = config
        self._client_factory = client_factory

    async def discover(
        self, category: ReportCategory, criteria: PennyStockEligibilityCriteria, limit: int
    ) -> tuple[UniverseEntry, ...]:
        if category is not ReportCategory.LOW_CAP_CRYPTO:
            return ()

        entries: list[UniverseEntry] = []
        seen: set[str] = set()

        async with self._client_factory(timeout=self._config.timeout) as client:
            for page in range(1, self._config.max_pages + 1):
                coins = await self._fetch_page(client, page)
                if not coins:
                    break

                exhausted = False
                for coin in coins:
                    market_cap = coin.get("market_cap")
                    if not isinstance(market_cap, int | float) or market_cap <= 0:
                        continue
                    if criteria.min_market_cap is not None and market_cap < criteria.min_market_cap:
                        exhausted = True  # sorted desc — nothing bigger remains
                        break
                    if criteria.max_market_cap is not None and market_cap > criteria.max_market_cap:
                        continue
                    entry = self._entry_from_coin(coin)
                    if entry is None or entry.ticker in seen:
                        continue
                    seen.add(entry.ticker)
                    entries.append(entry)
                    if len(entries) >= limit:
                        exhausted = True
                        break

                if exhausted:
                    break

        return tuple(entries)

    async def _fetch_page(self, client: httpx.AsyncClient, page: int) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": self._config.per_page, "page": page,
        }
        headers = {"User-Agent": self._config.user_agent}
        try:
            response = await client.get(f"{self._config.base_url}/coins/markets", params=params, headers=headers)
        except httpx.TimeoutException as exc:
            message = f"CoinGecko request timed out: {exc}"
            raise ProviderTimeoutError(message, provider_id=PROVIDER_ID) from exc
        except httpx.HTTPError as exc:
            message = f"CoinGecko request failed: {exc}"
            raise ProviderConnectionError(message, provider_id=PROVIDER_ID) from exc

        if response.status_code == 429:
            message = "CoinGecko rate-limited the request (HTTP 429)."
            raise ProviderRateLimitError(message, provider_id=PROVIDER_ID)
        if response.status_code != 200:
            message = f"CoinGecko returned HTTP {response.status_code}."
            raise ProviderResponseError(message, provider_id=PROVIDER_ID)
        try:
            payload = response.json()
        except ValueError as exc:
            message = f"CoinGecko response was not valid JSON: {exc}"
            raise ProviderResponseError(message, provider_id=PROVIDER_ID) from exc
        return payload if isinstance(payload, list) else []

    def _entry_from_coin(self, coin: dict[str, Any]) -> UniverseEntry | None:
        symbol = coin.get("symbol")
        name = coin.get("name")
        if not symbol or not name:
            return None
        if symbol.lower() in _STABLECOIN_SYMBOLS:
            return None
        ticker = f"{symbol.upper()}-USD"
        try:
            return UniverseEntry(ticker=ticker, name=name)
        except ValidationError:
            return None
