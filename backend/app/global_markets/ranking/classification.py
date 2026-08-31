"""RiskClassification — a deterministic, terminology-careful label
combining momentum and (inverted) risk scores.

A risk flag/classification is never proof of fraud or manipulation —
every member name and the function's own docstring are written to avoid
implying otherwise (explicit product requirement). A high-performing but
highly risky asset is never presented as an unqualified "best
opportunity": `STRONG_MOMENTUM_HIGH_RISK`/`EXTREME_MOMENTUM_EXTREME_RISK`
keep the risk half of the label exactly as visible as the momentum half.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["RiskClassification", "classify"]


class RiskClassification(StrEnum):
    STRONG_MOMENTUM_LOWER_RISK = "STRONG_MOMENTUM_LOWER_RISK"
    STRONG_MOMENTUM_MODERATE_RISK = "STRONG_MOMENTUM_MODERATE_RISK"
    STRONG_MOMENTUM_HIGH_RISK = "STRONG_MOMENTUM_HIGH_RISK"
    EXTREME_MOMENTUM_EXTREME_RISK = "EXTREME_MOMENTUM_EXTREME_RISK"
    MODERATE_MOMENTUM = "MODERATE_MOMENTUM"
    WEAK_MOMENTUM = "WEAK_MOMENTUM"
    INSUFFICIENT_CONFIDENCE = "INSUFFICIENT_CONFIDENCE"
    """Data was too incomplete to classify responsibly — never guessed,
    never silently defaulted to a more flattering tier."""


def classify(
    momentum_score: float,
    risk_score: float,
    data_confidence_score: float,
    *,
    min_confidence: float = 30.0,
    strong_momentum_threshold: float = 70.0,
    extreme_momentum_threshold: float = 85.0,
    moderate_momentum_threshold: float = 40.0,
    lower_risk_threshold: float = 35.0,
    moderate_risk_threshold: float = 70.0,
    extreme_risk_threshold: float = 85.0,
) -> RiskClassification:
    """Classify one asset from its already-computed, cross-sectionally
    scaled `momentum_score`/`risk_score`/`data_confidence_score`
    (0-100 each). `risk_score` follows `FactorScoringService`'s own
    convention — **higher `risk_score` means lower risk** (it is an
    inverted/"risk safety" scale); `danger` below un-inverts it back to
    an intuitive "higher means more dangerous" value purely for this
    function's own threshold comparisons.

    Every threshold is a keyword argument, never a literal buried in the
    branching logic — the "configurable, auditable" requirement, made
    concrete for classification the same way `RankingWeights` already
    makes it concrete for the final score.
    """
    if data_confidence_score < min_confidence:
        return RiskClassification.INSUFFICIENT_CONFIDENCE

    danger = 100.0 - risk_score

    if momentum_score >= extreme_momentum_threshold and danger >= extreme_risk_threshold:
        return RiskClassification.EXTREME_MOMENTUM_EXTREME_RISK

    if momentum_score >= strong_momentum_threshold:
        if danger < lower_risk_threshold:
            return RiskClassification.STRONG_MOMENTUM_LOWER_RISK
        if danger < moderate_risk_threshold:
            return RiskClassification.STRONG_MOMENTUM_MODERATE_RISK
        return RiskClassification.STRONG_MOMENTUM_HIGH_RISK

    if momentum_score >= moderate_momentum_threshold:
        return RiskClassification.MODERATE_MOMENTUM

    return RiskClassification.WEAK_MOMENTUM
