"""Tests for `WeightedRankingEngine` (`app.global_markets.ranking.engine`)."""

from __future__ import annotations

from app.global_markets.ranking.engine import WeightedRankingEngine
from app.global_markets.ranking.models import FactorScore, RankingFactor, RankingWeights


def _score(factor: RankingFactor, value: float) -> FactorScore:
    return FactorScore(factor=factor, value=value)


def test_higher_weighted_average_ranks_first() -> None:
    weights = RankingWeights(weights={RankingFactor.PRICE_PERFORMANCE: 1.0})
    engine = WeightedRankingEngine(weights)

    ranked = engine.rank(
        {
            "LOW": (_score(RankingFactor.PRICE_PERFORMANCE, 30.0),),
            "HIGH": (_score(RankingFactor.PRICE_PERFORMANCE, 90.0),),
        }
    )

    assert [entry.ticker for entry in ranked] == ["HIGH", "LOW"]
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2


def test_combines_multiple_factors_by_weight() -> None:
    weights = RankingWeights(weights={RankingFactor.PRICE_PERFORMANCE: 3.0, RankingFactor.RISK: 1.0})
    engine = WeightedRankingEngine(weights)

    ranked = engine.rank(
        {
            "A": (_score(RankingFactor.PRICE_PERFORMANCE, 80.0), _score(RankingFactor.RISK, 20.0)),
        }
    )

    expected = (80.0 * 3.0 + 20.0 * 1.0) / (3.0 + 1.0)
    assert ranked[0].final_score == round(expected, 4)


def test_a_factor_with_no_configured_weight_contributes_nothing() -> None:
    weights = RankingWeights(weights={RankingFactor.PRICE_PERFORMANCE: 1.0})
    engine = WeightedRankingEngine(weights)

    ranked = engine.rank(
        {
            "A": (
                _score(RankingFactor.PRICE_PERFORMANCE, 50.0),
                _score(RankingFactor.NEWS_EVENT_IMPACT, 100.0),  # unweighted, must not move the score
            ),
        }
    )

    assert ranked[0].final_score == 50.0


def test_unweighted_asset_scores_zero_but_is_never_dropped() -> None:
    weights = RankingWeights(weights={})
    engine = WeightedRankingEngine(weights)

    ranked = engine.rank({"A": (_score(RankingFactor.PRICE_PERFORMANCE, 99.0),)})

    assert len(ranked) == 1
    assert ranked[0].final_score == 0.0
    assert ranked[0].factor_scores[0].value == 99.0  # still carried for inspection


def test_ties_break_by_ticker_ascending_deterministically() -> None:
    weights = RankingWeights(weights={RankingFactor.PRICE_PERFORMANCE: 1.0})
    engine = WeightedRankingEngine(weights)

    ranked = engine.rank(
        {
            "ZETA": (_score(RankingFactor.PRICE_PERFORMANCE, 50.0),),
            "ALPHA": (_score(RankingFactor.PRICE_PERFORMANCE, 50.0),),
            "BETA": (_score(RankingFactor.PRICE_PERFORMANCE, 50.0),),
        }
    )

    assert [entry.ticker for entry in ranked] == ["ALPHA", "BETA", "ZETA"]


def test_ranking_is_reproducible_across_repeated_calls() -> None:
    """Auditability requirement: identical input always produces identical output order."""
    weights = RankingWeights(weights={RankingFactor.MOMENTUM: 2.0, RankingFactor.RISK: 1.0})
    engine = WeightedRankingEngine(weights)
    assets = {
        "AAA": (_score(RankingFactor.MOMENTUM, 70.0), _score(RankingFactor.RISK, 40.0)),
        "BBB": (_score(RankingFactor.MOMENTUM, 65.0), _score(RankingFactor.RISK, 10.0)),
        "CCC": (_score(RankingFactor.MOMENTUM, 65.0), _score(RankingFactor.RISK, 10.0)),
    }

    first = engine.rank(assets)
    second = engine.rank(assets)

    assert [entry.ticker for entry in first] == [entry.ticker for entry in second]
    assert [entry.final_score for entry in first] == [entry.final_score for entry in second]


def test_ranks_are_assigned_sequentially_starting_at_one() -> None:
    weights = RankingWeights(weights={RankingFactor.PRICE_PERFORMANCE: 1.0})
    engine = WeightedRankingEngine(weights)

    ranked = engine.rank(
        {f"T{i}": (_score(RankingFactor.PRICE_PERFORMANCE, float(i)),) for i in range(5)}
    )

    assert [entry.rank for entry in ranked] == [1, 2, 3, 4, 5]


def test_weight_for_returns_zero_for_an_unconfigured_factor() -> None:
    weights = RankingWeights(weights={RankingFactor.MOMENTUM: 5.0})
    assert weights.weight_for(RankingFactor.RISK) == 0.0
    assert weights.weight_for(RankingFactor.MOMENTUM) == 5.0
