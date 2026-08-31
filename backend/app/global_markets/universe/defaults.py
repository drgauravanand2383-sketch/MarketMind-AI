"""DEFAULT_UNIVERSES — the starter candidate ticker set per `ReportCategory`.

**Every ticker below was individually live-verified** (a real quote
fetched via the actual `YahooFinanceProvider` against the actual Yahoo
Finance chart endpoint) before being hardcoded here — never guessed or
recalled from training data, per this module's own "the AI must never
fabricate financial facts" requirement.

**The five main categories** (`INDIA_EQUITY`/`US_EQUITY`/`CHINA_EQUITY`/
`FOREX`/`CRYPTO`) get a real, verified 10-ticker starter universe each —
large, unambiguous, well-known names (India/US/China large-caps by
market presence, major currency pairs, major cryptocurrencies by market
capitalization). This is a genuine, working seed set, not a placeholder
— but it is deliberately small; expanding it to a fuller candidate pool
(the 20-50 names a real "Top 15" selection should plausibly draw from)
is intentionally left as configuration to extend, not an engineering
task to guess at here.

**The four penny/micro-cap categories are deliberately left empty.**
Identifying genuine, currently-listed, non-delisted penny/micro-cap
candidates requires a real screening data source (minimum price/volume/
market-cap filters applied *before* candidates are even proposed) — an
LLM recalling specific small-cap tickers from training data is exactly
the kind of unverifiable, likely-stale-or-wrong "fact" this module's own
"never fabricate" principle exists to prevent (a training-data-recalled
penny stock is disproportionately likely to have since been delisted,
acquired, or renamed). `UniverseRegistry.get()` correctly returns an
empty tuple for these four categories — an honest, explicit gap, not a
silent one — until a real screening integration (a later phase) can
supply verified candidates. Every other Phase 1/2 component for these
categories (`PennyStockEligibilityCriteria`, `ConfigurableEligibilityProvider`)
is already built and tested against fixture data, ready to receive a
real universe with no further code change.
"""

from __future__ import annotations

from app.global_markets.models import ReportCategory
from app.global_markets.universe.models import UniverseEntry

__all__ = ["DEFAULT_UNIVERSES"]

DEFAULT_UNIVERSES: dict[ReportCategory, tuple[UniverseEntry, ...]] = {
    ReportCategory.INDIA_EQUITY: (
        UniverseEntry(ticker="RELIANCE.NS", name="Reliance Industries"),
        UniverseEntry(ticker="TCS.NS", name="Tata Consultancy Services"),
        UniverseEntry(ticker="HDFCBANK.NS", name="HDFC Bank"),
        UniverseEntry(ticker="ICICIBANK.NS", name="ICICI Bank"),
        UniverseEntry(ticker="INFY.NS", name="Infosys"),
        UniverseEntry(ticker="ITC.NS", name="ITC Limited"),
        UniverseEntry(ticker="SBIN.NS", name="State Bank of India"),
        UniverseEntry(ticker="BHARTIARTL.NS", name="Bharti Airtel"),
        UniverseEntry(ticker="LT.NS", name="Larsen & Toubro"),
        UniverseEntry(ticker="HINDUNILVR.NS", name="Hindustan Unilever"),
    ),
    ReportCategory.US_EQUITY: (
        UniverseEntry(ticker="AAPL", name="Apple Inc."),
        UniverseEntry(ticker="MSFT", name="Microsoft Corporation"),
        UniverseEntry(ticker="NVDA", name="NVIDIA Corporation"),
        UniverseEntry(ticker="GOOGL", name="Alphabet Inc."),
        UniverseEntry(ticker="AMZN", name="Amazon.com, Inc."),
        UniverseEntry(ticker="META", name="Meta Platforms, Inc."),
        UniverseEntry(ticker="TSLA", name="Tesla, Inc."),
        UniverseEntry(ticker="BRK-B", name="Berkshire Hathaway Inc."),
        UniverseEntry(ticker="JPM", name="JPMorgan Chase & Co."),
        UniverseEntry(ticker="V", name="Visa Inc."),
    ),
    ReportCategory.CHINA_EQUITY: (
        UniverseEntry(ticker="600519.SS", name="Kweichow Moutai"),
        UniverseEntry(ticker="000858.SZ", name="Wuliangye Yibin"),
        UniverseEntry(ticker="601398.SS", name="Industrial and Commercial Bank of China"),
        UniverseEntry(ticker="600036.SS", name="China Merchants Bank"),
        UniverseEntry(ticker="000333.SZ", name="Midea Group"),
        UniverseEntry(ticker="601288.SS", name="Agricultural Bank of China"),
        UniverseEntry(ticker="600028.SS", name="China Petroleum & Chemical (Sinopec)"),
        UniverseEntry(ticker="601988.SS", name="Bank of China"),
        UniverseEntry(ticker="000651.SZ", name="Gree Electric Appliances"),
        UniverseEntry(ticker="600030.SS", name="CITIC Securities"),
    ),
    ReportCategory.FOREX: (
        UniverseEntry(ticker="EURUSD=X", name="Euro / US Dollar"),
        UniverseEntry(ticker="GBPUSD=X", name="British Pound / US Dollar"),
        UniverseEntry(ticker="USDJPY=X", name="US Dollar / Japanese Yen"),
        UniverseEntry(ticker="AUDUSD=X", name="Australian Dollar / US Dollar"),
        UniverseEntry(ticker="USDCAD=X", name="US Dollar / Canadian Dollar"),
        UniverseEntry(ticker="USDCHF=X", name="US Dollar / Swiss Franc"),
        UniverseEntry(ticker="NZDUSD=X", name="New Zealand Dollar / US Dollar"),
        UniverseEntry(ticker="USDINR=X", name="US Dollar / Indian Rupee"),
        UniverseEntry(ticker="USDCNY=X", name="US Dollar / Chinese Yuan"),
        UniverseEntry(ticker="EURGBP=X", name="Euro / British Pound"),
    ),
    ReportCategory.CRYPTO: (
        UniverseEntry(ticker="BTC-USD", name="Bitcoin"),
        UniverseEntry(ticker="ETH-USD", name="Ethereum"),
        UniverseEntry(ticker="BNB-USD", name="BNB"),
        UniverseEntry(ticker="SOL-USD", name="Solana"),
        UniverseEntry(ticker="XRP-USD", name="XRP"),
        UniverseEntry(ticker="ADA-USD", name="Cardano"),
        UniverseEntry(ticker="DOGE-USD", name="Dogecoin"),
        UniverseEntry(ticker="AVAX-USD", name="Avalanche"),
        UniverseEntry(ticker="DOT-USD", name="Polkadot"),
        UniverseEntry(ticker="LINK-USD", name="Chainlink"),
    ),
    # Deliberately empty — see this module's own docstring.
    ReportCategory.INDIA_PENNY_STOCK: (),
    ReportCategory.US_PENNY_STOCK: (),
    ReportCategory.CHINA_PENNY_STOCK: (),
    ReportCategory.LOW_CAP_CRYPTO: (),
}
