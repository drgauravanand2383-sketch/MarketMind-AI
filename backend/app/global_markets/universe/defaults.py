"""DEFAULT_UNIVERSES — the starter candidate ticker set per `ReportCategory`.

**Every ticker below was individually live-verified** (real daily history
fetched via the actual `YahooFinanceProvider` against the actual Yahoo
Finance chart endpoint, on 2026-09-02) before being hardcoded here —
never guessed or recalled from training data, per this module's own "the
AI must never fabricate financial facts" requirement.

**The five main categories** (`INDIA_EQUITY`/`US_EQUITY`/`CHINA_EQUITY`/
`FOREX`/`CRYPTO`) each get a real, verified **15-ticker** starter
universe — large, unambiguous, well-known names (India/US/China
large-caps by market presence, major currency pairs, major
cryptocurrencies by market capitalization). This comfortably covers a
"Top 15" selection (`REPORT_CATEGORY_DEFINITIONS[...].top_n == 15`).
Extending any of these to a still-larger candidate pool remains
configuration to add, not an engineering task to guess at here.

**The three equity penny/micro-cap categories now carry a small,
FALLBACK-ONLY static universe.** The primary candidate source for these
categories is live external discovery
(`ScreeningProvider.discover()`, wired in `_resolve_universe`); the
static list here is used **only** when that discovery raises or returns
nothing (e.g. the Yahoo screener rate-limiting under load). Every entry
was live-verified on 2026-09-02 as currently listed, actively trading
(250+ daily bars), and — at verification time — priced under its
market's approved `max_price` gate (`DEFAULT_ELIGIBILITY_CRITERIA`):
US < $5.00, India < Rs 20, China < CNY 10. The downstream
`ConfigurableEligibilityProvider` re-checks price (and every other
criterion) fresh each run, so a name that has since drifted above its
cap is simply filtered out — never silently ranked. These lists are
deliberately short: they hold only names that could be verified, not
padded to reach 20. If a run's discovery fails *and* fewer than
`top_n` of these pass eligibility, the honest result is a shorter list,
not fabricated filler.

Because the live pipeline has no market-cap data source yet
(`NormalizedAssetSnapshot.market_cap` is never populated — see
`DEFAULT_ELIGIBILITY_CRITERIA`'s own caveat), the `min/max_market_cap`
bands cannot currently reject a candidate. Some fallback names below are
therefore large companies that merely trade at a low *nominal* share
price (notably several Shanghai/Shenzhen-listed banks and utilities);
they satisfy the price-based gate the system enforces today. This is a
known data limitation, not an oversight, and it affects the fallback
list only — live discovery applies the market-cap band at the vendor.

**`LOW_CAP_CRYPTO` remains deliberately empty.** Its eligibility gate
depends entirely on market-cap / daily-volume data the pipeline cannot
supply today, so `ConfigurableEligibilityProvider` structurally rejects
every candidate for it (`data_completeness_ratio` below the 0.5
minimum). Adding tickers would only produce candidates that can never
pass — exactly the fabrication this module exists to prevent. It stays
empty until a market-cap-capable crypto source is wired in.
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
        UniverseEntry(ticker="BAJFINANCE.NS", name="Bajaj Finance"),
        UniverseEntry(ticker="KOTAKBANK.NS", name="Kotak Mahindra Bank"),
        UniverseEntry(ticker="AXISBANK.NS", name="Axis Bank"),
        UniverseEntry(ticker="MARUTI.NS", name="Maruti Suzuki India"),
        UniverseEntry(ticker="SUNPHARMA.NS", name="Sun Pharmaceutical Industries"),
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
        UniverseEntry(ticker="UNH", name="UnitedHealth Group Incorporated"),
        UniverseEntry(ticker="XOM", name="Exxon Mobil Corporation"),
        UniverseEntry(ticker="MA", name="Mastercard Incorporated"),
        UniverseEntry(ticker="JNJ", name="Johnson & Johnson"),
        UniverseEntry(ticker="AVGO", name="Broadcom Inc."),
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
        UniverseEntry(ticker="601857.SS", name="PetroChina"),
        UniverseEntry(ticker="600900.SS", name="China Yangtze Power"),
        UniverseEntry(ticker="601318.SS", name="Ping An Insurance"),
        UniverseEntry(ticker="600887.SS", name="Inner Mongolia Yili Industrial Group"),
        UniverseEntry(ticker="000001.SZ", name="Ping An Bank"),
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
        UniverseEntry(ticker="EURJPY=X", name="Euro / Japanese Yen"),
        UniverseEntry(ticker="GBPJPY=X", name="British Pound / Japanese Yen"),
        UniverseEntry(ticker="EURCHF=X", name="Euro / Swiss Franc"),
        UniverseEntry(ticker="AUDJPY=X", name="Australian Dollar / Japanese Yen"),
        UniverseEntry(ticker="USDSGD=X", name="US Dollar / Singapore Dollar"),
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
        UniverseEntry(ticker="LTC-USD", name="Litecoin"),
        UniverseEntry(ticker="BCH-USD", name="Bitcoin Cash"),
        UniverseEntry(ticker="TRX-USD", name="TRON"),
        UniverseEntry(ticker="XLM-USD", name="Stellar"),
        UniverseEntry(ticker="ATOM-USD", name="Cosmos"),
    ),
    # FALLBACK ONLY — live discovery (`_resolve_universe`) is the primary
    # source. See this module's docstring. Verified 2026-09-02.
    ReportCategory.INDIA_PENNY_STOCK: (
        UniverseEntry(ticker="IDEA.NS", name="Vodafone Idea"),
        UniverseEntry(ticker="JPPOWER.NS", name="Jaiprakash Power Ventures"),
        UniverseEntry(ticker="RTNPOWER.NS", name="RattanIndia Power"),
        UniverseEntry(ticker="GTLINFRA.NS", name="GTL Infrastructure"),
        UniverseEntry(ticker="ALOKINDS.NS", name="Alok Industries"),
        UniverseEntry(ticker="RCOM.NS", name="Reliance Communications"),
        UniverseEntry(ticker="IRB.NS", name="IRB Infrastructure Developers"),
    ),
    ReportCategory.US_PENNY_STOCK: (
        UniverseEntry(ticker="PLUG", name="Plug Power Inc."),
        UniverseEntry(ticker="LCID", name="Lucid Group, Inc."),
        UniverseEntry(ticker="KOS", name="Kosmos Energy Ltd."),
        UniverseEntry(ticker="BBAI", name="BigBear.ai Holdings, Inc."),
        UniverseEntry(ticker="DNN", name="Denison Mines Corp."),
        UniverseEntry(ticker="SNDL", name="SNDL Inc."),
        UniverseEntry(ticker="NIO", name="NIO Inc. (ADR)"),
        UniverseEntry(ticker="GRAB", name="Grab Holdings Limited"),
    ),
    ReportCategory.CHINA_PENNY_STOCK: (
        UniverseEntry(ticker="601668.SS", name="China State Construction Engineering"),
        UniverseEntry(ticker="600050.SS", name="China United Network Communications"),
        UniverseEntry(ticker="601169.SS", name="Bank of Beijing"),
        UniverseEntry(ticker="601328.SS", name="Bank of Communications"),
        UniverseEntry(ticker="600018.SS", name="Shanghai International Port Group"),
        UniverseEntry(ticker="601818.SS", name="China Everbright Bank"),
        UniverseEntry(ticker="000725.SZ", name="BOE Technology Group"),
        UniverseEntry(ticker="600795.SS", name="GD Power Development"),
        UniverseEntry(ticker="601111.SS", name="Air China"),
        UniverseEntry(ticker="601006.SS", name="Daqin Railway"),
        UniverseEntry(ticker="600015.SS", name="Hua Xia Bank"),
        UniverseEntry(ticker="601998.SS", name="China CITIC Bank"),
    ),
    # Deliberately empty — eligibility structurally rejects every candidate
    # without a market-cap source. See this module's docstring.
    ReportCategory.LOW_CAP_CRYPTO: (),
}
