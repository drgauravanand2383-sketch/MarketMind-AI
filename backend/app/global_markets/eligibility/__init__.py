"""Penny/micro-cap eligibility foundation — see
`app.global_markets.eligibility.provider.PennyStockEligibilityProvider`.
"""

from app.global_markets.eligibility.defaults import (
    DEFAULT_ELIGIBILITY_CRITERIA,
    PENNY_STOCK_MARKET_FOR_CATEGORY,
    criteria_for_category,
    eligibility_provider_for_category,
)
from app.global_markets.eligibility.models import (
    EligibilityCheckResult,
    PennyStockEligibilityCriteria,
    PennyStockMarket,
)
from app.global_markets.eligibility.provider import (
    ConfigurableEligibilityProvider,
    PennyStockEligibilityProvider,
)

__all__ = [
    "PennyStockMarket",
    "PennyStockEligibilityCriteria",
    "EligibilityCheckResult",
    "PennyStockEligibilityProvider",
    "ConfigurableEligibilityProvider",
    "DEFAULT_ELIGIBILITY_CRITERIA",
    "PENNY_STOCK_MARKET_FOR_CATEGORY",
    "eligibility_provider_for_category",
    "criteria_for_category",
]
