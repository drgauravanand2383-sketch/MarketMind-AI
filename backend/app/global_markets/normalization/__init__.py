"""Normalization: raw `MarketQuote`/`HistoricalSeries` -> `NormalizedAssetSnapshot`."""

from __future__ import annotations

from app.global_markets.normalization.normalizer import MarketDataNormalizer

__all__ = ["MarketDataNormalizer"]
