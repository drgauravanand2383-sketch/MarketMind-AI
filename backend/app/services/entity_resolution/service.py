"""Entity Resolution Service (Milestone 12).

`EntityResolutionService.resolve()` turns free text (an article's title +
body) into an `EntityResolutionResult`: zero or more candidate companies,
transparently scored, classified into an explicit confidence tier. No LLM
call, no fuzzy/probabilistic string matching (e.g. edit distance) —
candidate generation is deterministic whole-word matching against the
static `CompanyReference` reference set, the same word-boundary technique
`MarketIntelligenceEngine`/`EvidenceEngine` already use (kept consistent
so all three engines agree on what counts as a "match").

Isolated by design: this module knows nothing about RSS parsing,
embeddings, Chroma, or Research report rendering — every caller (ingestion
enrichment, backfill, Research retrieval) injects this service and calls
only `resolve()`/`lookup_by_name_or_ticker()`.
"""

from __future__ import annotations

import re

from app.services.entity_resolution.models import (
    CompanyReference,
    ConfidenceTier,
    EntityCandidate,
    EntityResolutionContext,
    EntityResolutionResult,
    ResolutionMethod,
)
from app.services.entity_resolution.reference_data import get_company_reference_data

__all__ = [
    "DEFAULT_HIGH_THRESHOLD",
    "DEFAULT_MEDIUM_THRESHOLD",
    "DEFAULT_MAX_CANDIDATES",
    "EntityResolutionService",
]

# Base score per matching signal, weakest to strongest evidence. A ticker
# mention alone is the weakest signal (short, sometimes an ordinary English
# word/abbreviation out of context) — matched case-sensitively (see
# `_find_ticker_occurrences`) specifically to offset that weakness, not
# because it's inherently more trustworthy than a name match.
_METHOD_BASE_SCORE: dict[ResolutionMethod, float] = {
    ResolutionMethod.EXACT_NAME: 0.90,
    ResolutionMethod.LEGAL_NAME: 0.85,
    ResolutionMethod.ALIAS: 0.75,
    ResolutionMethod.TICKER: 0.65,
}

_TITLE_BONUS = 0.15
_OCCURRENCE_BONUS_PER_EXTRA = 0.03
_OCCURRENCE_BONUS_CAP = 0.12
# Applied to every candidate's score when more than one distinct company is
# found in the same text — deliberately reduces confidence under ambiguity
# (this milestone's own §6/§18 "ambiguous company remains unresolved/
# medium-confidence rather than being guessed" requirement) rather than
# picking a winner outright.
_AMBIGUITY_PENALTY = 0.85
# If the top two candidates' scores are within this margin, the result is
# treated as ambiguous even when the top score alone would clear
# `high_threshold` — a second real explanation is too close to rule out.
_AMBIGUITY_MARGIN = 0.15

DEFAULT_HIGH_THRESHOLD = 0.85
DEFAULT_MEDIUM_THRESHOLD = 0.5
DEFAULT_MAX_CANDIDATES = 5

_WORD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _word_pattern(term: str) -> re.Pattern[str]:
    """Whole-word/phrase pattern for `term`, cached (mirrors
    MarketIntelligenceEngine._contains_any_keyword's own technique, so a
    short term like "IT" never substring-matches inside "within")."""
    pattern = _WORD_RE_CACHE.get(term)
    if pattern is None:
        pattern = re.compile(rf"\b{re.escape(term)}\b")
        _WORD_RE_CACHE[term] = pattern
    return pattern


class EntityResolutionService:
    """Resolves free text to canonical company entities, deterministically."""

    def __init__(
        self,
        references: tuple[CompanyReference, ...] | None = None,
        *,
        high_threshold: float = DEFAULT_HIGH_THRESHOLD,
        medium_threshold: float = DEFAULT_MEDIUM_THRESHOLD,
        max_candidates: int = DEFAULT_MAX_CANDIDATES,
    ) -> None:
        """Initialize the service.

        Args:
            references: The canonical company reference set to match
                against. Defaults to `get_company_reference_data()`
                (the production reference set) when None/omitted; tests
                inject a small, controlled set instead so assertions
                don't depend on the production reference data's exact
                contents. `None` (not a mutable-default-style constant)
                is used here deliberately — see
                `app.services.entity_resolution.reference_data`'s own
                docstring for why the production set can't be a plain
                default-argument value without creating a circular import.
            high_threshold: Minimum score (after ambiguity margin check)
                for `ConfidenceTier.HIGH`.
            medium_threshold: Minimum score for `ConfidenceTier.MEDIUM`.
            max_candidates: Maximum total candidates
                (`result.candidates`, including primary) returned.
        """
        if not (0.0 <= medium_threshold <= high_threshold <= 1.0):
            raise ValueError(
                "Require 0.0 <= medium_threshold <= high_threshold <= 1.0; "
                f"got medium_threshold={medium_threshold!r}, high_threshold={high_threshold!r}."
            )
        if max_candidates < 1:
            raise ValueError(f"max_candidates must be >= 1; got {max_candidates!r}.")

        self._references = references if references is not None else get_company_reference_data()
        self._high_threshold = high_threshold
        self._medium_threshold = medium_threshold
        self._max_candidates = max_candidates

    def resolve(
        self, text: str, context: EntityResolutionContext | None = None
    ) -> EntityResolutionResult:
        """Resolve `text` to zero or more candidate companies.

        Args:
            text: The body text to scan (e.g. a knowledge record's title +
                summary, already joined). Safe on empty/malformed input —
                never raises for any string value.
            context: Optional extra context. `context.title`, when given,
                is scored separately for the title-vs-body weighting
                requirement; otherwise `text` alone is scanned with no
                title bonus available.

        Returns:
            An EntityResolutionResult. `primary`/`secondary` are populated
            only when `confidence_tier` is HIGH or MEDIUM; `candidates`
            always lists every match considered, for transparency.
        """
        title = (context.title if context is not None else None) or ""
        combined = f"{title}\n{text}" if title else text

        candidates = [
            candidate
            for reference in self._references
            if (candidate := self._score_reference(reference, combined, title)) is not None
        ]

        if not candidates:
            return EntityResolutionResult(
                confidence_tier=ConfidenceTier.UNRESOLVED,
                reason="No candidate entities matched this text.",
            )

        if len(candidates) > 1:
            candidates = [
                candidate.model_copy(
                    update={"score": round(candidate.score * _AMBIGUITY_PENALTY, 4)}
                )
                for candidate in candidates
            ]

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        candidates = candidates[: self._max_candidates]

        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        ambiguous = second is not None and (best.score - second.score) < _AMBIGUITY_MARGIN

        if best.score >= self._high_threshold and not ambiguous:
            tier = ConfidenceTier.HIGH
        elif best.score >= self._medium_threshold:
            tier = ConfidenceTier.MEDIUM
        else:
            tier = ConfidenceTier.LOW

        if tier in (ConfidenceTier.HIGH, ConfidenceTier.MEDIUM):
            primary = best
            secondary = tuple(
                candidate
                for candidate in candidates[1:]
                if candidate.score >= self._medium_threshold
            )
            ambiguity_note = (
                ", ambiguous with a close second candidate"
                if ambiguous and tier == ConfidenceTier.MEDIUM
                else ""
            )
            reason = (
                f"{best.canonical_name} matched via {best.method.value} "
                f"(score={best.score:.2f}{ambiguity_note})."
            )
        else:
            primary = None
            secondary = ()
            reason = (
                f"Best candidate {best.canonical_name!r} scored {best.score:.2f}, "
                f"below the medium-confidence threshold ({self._medium_threshold:.2f}); "
                "not automatically attached."
            )

        return EntityResolutionResult(
            primary=primary,
            secondary=secondary,
            confidence_tier=tier,
            candidates=tuple(candidates),
            reason=reason,
        )

    def list_references(self) -> tuple[CompanyReference, ...]:
        """Every canonical entity in this service's reference set.

        Milestone 13: lets a caller that needs to act on "every known
        canonical company" (e.g. the market-data refresh workflow, §13)
        enumerate them without reaching into this service's private
        `_references` attribute.
        """
        return self._references

    def get_by_entity_id(self, entity_id: str) -> CompanyReference | None:
        """Look up a canonical entity by its own stable `entity_id`.

        Milestone 13: the entry point market-data integration uses to map
        an already-resolved entity (e.g. a Research request's own
        `company_overview.resolved_entity_id`, or one of this service's
        own reference-set ids) to `.ticker`/`.exchange`/`.currency` —
        without touching the canonical identity model itself, and without
        ever guessing: an unknown `entity_id` returns `None`, exactly
        like `lookup_by_name_or_ticker`'s own "not found" contract.
        """
        for reference in self._references:
            if reference.entity_id == entity_id:
                return reference
        return None

    def lookup_by_name_or_ticker(
        self, name: str | None, ticker: str | None = None
    ) -> CompanyReference | None:
        """Directly look up a canonical entity by an already-known name/ticker.

        Distinct from `resolve()`: this is for resolving an *input
        identifier* a caller already supplied (e.g. a Research request's
        `company_name`/`ticker`), not for scanning free text for
        candidates — so no scoring or ambiguity handling applies, only a
        direct case-insensitive match. Matches `name` against
        canonical_name/legal_name/aliases (exact, or substring in either
        direction — the same tolerance
        `CompanyResearchAgent`'s existing `resolve_company_name` already
        uses) and `ticker` against `.ticker` (exact, case-insensitive).

        Returns:
            The matching CompanyReference, or None if neither `name` nor
            `ticker` resolves to any entry in the reference set.
        """
        normalized_name = (name or "").strip().lower()
        normalized_ticker = (ticker or "").strip().lower()

        for reference in self._references:
            ref_ticker = (reference.ticker or "").lower()
            if normalized_ticker and ref_ticker == normalized_ticker:
                return reference
            if normalized_name:
                names = (reference.canonical_name, reference.legal_name or "", *reference.aliases)
                for candidate_name in names:
                    candidate_lower = candidate_name.lower()
                    if not candidate_lower:
                        continue
                    if (
                        normalized_name == candidate_lower
                        or normalized_name in candidate_lower
                        or candidate_lower in normalized_name
                    ):
                        return reference
        return None

    def _score_reference(
        self, reference: CompanyReference, combined_text: str, title: str
    ) -> EntityCandidate | None:
        """Score one CompanyReference against `combined_text`, or return
        None if nothing about it matched at all."""
        matches: list[tuple[ResolutionMethod, str, int]] = []

        name_method = ResolutionMethod.EXACT_NAME
        matches.extend(self._find_occurrences(reference.canonical_name, combined_text, name_method))
        if reference.legal_name:
            legal_method = ResolutionMethod.LEGAL_NAME
            legal_text = reference.legal_name
            matches.extend(self._find_occurrences(legal_text, combined_text, legal_method))
        for alias in reference.aliases:
            # An alias that's *literally* the ticker spelled out in the
            # same upper-case form (COMPANY_KEYWORDS commonly includes it,
            # e.g. Salesforce's own ("Salesforce", "CRM")) is deliberately
            # not matched here: case-insensitive alias matching would
            # otherwise let a short ticker-as-alias like "CRM" false-match
            # ordinary lowercase text ("crm software"), defeating
            # `_find_ticker_occurrences`'s own case-sensitive safeguard
            # below. Exact (not `.upper()`-normalized) comparison matters:
            # normalizing would also wrongly skip a genuine mixed-case name
            # alias like "Dell" just because it uppercases to the same
            # string as the ticker "DELL". The ticker itself is still
            # matched, just only via that stricter, case-sensitive path.
            if alias == reference.ticker:
                continue
            matches.extend(self._find_occurrences(alias, combined_text, ResolutionMethod.ALIAS))
        if reference.ticker:
            matches.extend(self._find_ticker_occurrences(reference.ticker, combined_text))

        if not matches:
            return None

        # The strongest signal among every method that matched this
        # reference (e.g. both a name match and a ticker match) wins.
        best_method = max(matches, key=lambda match: _METHOD_BASE_SCORE[match[0]])[0]

        matched_terms = tuple(sorted({term for _, term, _ in matches}))
        total_occurrences = sum(count for _, _, count in matches)
        title_match = bool(title) and any(
            _word_pattern(term).search(title) is not None for _, term, _ in matches
        )

        score = _METHOD_BASE_SCORE[best_method]
        if title_match:
            score += _TITLE_BONUS
        occurrence_bonus = min(
            _OCCURRENCE_BONUS_CAP, max(0, total_occurrences - 1) * _OCCURRENCE_BONUS_PER_EXTRA
        )
        score = min(1.0, score + occurrence_bonus)

        return EntityCandidate(
            entity_id=reference.entity_id,
            canonical_name=reference.canonical_name,
            ticker=reference.ticker,
            method=best_method,
            score=round(score, 4),
            matched_terms=matched_terms,
            occurrence_count=total_occurrences,
            title_match=title_match,
        )

    def _find_occurrences(
        self, term: str, text: str, method: ResolutionMethod
    ) -> list[tuple[ResolutionMethod, str, int]]:
        """Case-insensitive whole-word/phrase occurrence count for `term` in `text`."""
        if not term or not text:
            return []
        count = len(_word_pattern(term.lower()).findall(text.lower()))
        return [(method, term, count)] if count else []

    def _find_ticker_occurrences(
        self, ticker: str, text: str
    ) -> list[tuple[ResolutionMethod, str, int]]:
        """Case-*sensitive* whole-word ticker match — deliberately stricter
        than name/alias matching (see `_METHOD_BASE_SCORE`'s own docstring):
        a short ticker like "CRM" is also an ordinary English abbreviation
        ("CRM software"); requiring the exact upper-case form real financial
        text actually uses avoids that class of false positive."""
        if not ticker or not text:
            return []
        count = len(_word_pattern(ticker).findall(text))
        return [(ResolutionMethod.TICKER, ticker, count)] if count else []
