"""Unit tests for EntityResolutionService.

Uses a small, controlled CompanyReference fixture set (not the production
reference data from `get_company_reference_data()`) so every assertion is
independent of what real companies happen to be in the production
reference set — exactly the testability `EntityResolutionService.__init__`'s
own `references` parameter is documented to exist for.
"""

from __future__ import annotations

from app.services.entity_resolution.models import (
    CompanyReference,
    ConfidenceTier,
    EntityResolutionContext,
    ResolutionMethod,
)
from app.services.entity_resolution.service import EntityResolutionService


def _references() -> tuple[CompanyReference, ...]:
    return (
        CompanyReference(
            entity_id="acme",
            canonical_name="Acme Corporation",
            legal_name="Acme Corporation Inc.",
            ticker="ACME",
            exchange="NASDAQ",
            country="United States",
            sector="Technology",
            industry="Software",
            aliases=("Acme",),
        ),
        CompanyReference(
            entity_id="globex",
            canonical_name="Globex Corporation",
            ticker="GLBX",
            exchange="NYSE",
            country="United States",
            sector="Industrials",
            industry="Manufacturing",
            aliases=("Globex",),
        ),
        # A ticker that's also an ordinary English word — the false-positive
        # scenario `_find_ticker_occurrences`'s case-sensitive matching
        # exists to prevent.
        CompanyReference(
            entity_id="initech",
            canonical_name="Initech Corporation",
            ticker="IT",
            exchange="NYSE",
            aliases=("Initech",),
        ),
    )


def _service(**overrides: object) -> EntityResolutionService:
    return EntityResolutionService(_references(), **overrides)  # type: ignore[arg-type]


# --- resolve(): candidate generation and scoring ---------------------------


def test_resolve_exact_canonical_name_is_high_confidence() -> None:
    service = _service()
    result = service.resolve(
        "Acme Corporation reported record profits this quarter.",
        EntityResolutionContext(title="Acme Corporation reported record profits"),
    )

    assert result.confidence_tier == ConfidenceTier.HIGH
    assert result.primary is not None
    assert result.primary.entity_id == "acme"
    assert result.primary.method == ResolutionMethod.EXACT_NAME


def test_resolve_alias_match() -> None:
    service = _service()
    result = service.resolve("Acme unveiled a new product line today.", EntityResolutionContext(title="Acme unveiled a new product line"))

    assert result.primary is not None
    assert result.primary.entity_id == "acme"
    assert result.primary.method == ResolutionMethod.ALIAS


def test_resolve_legal_name_match() -> None:
    service = _service()
    result = service.resolve(
        "Acme Corporation Inc. filed its annual report.",
        EntityResolutionContext(title="Acme Corporation Inc. filed its annual report"),
    )

    assert result.primary is not None
    assert result.primary.entity_id == "acme"


def test_resolve_ticker_match_uppercase_in_real_financial_text() -> None:
    service = _service()
    result = service.resolve(
        "Shares of ACME (NASDAQ: ACME) rose 4% in afternoon trading.",
        EntityResolutionContext(title="Shares of ACME rose 4% in afternoon trading"),
    )

    assert result.primary is not None
    assert result.primary.entity_id == "acme"


def test_resolve_ticker_lowercase_does_not_false_match() -> None:
    """A ticker that's also an ordinary English word ("IT") must not
    match generic lowercase text mentioning it — the exact false-positive
    class this milestone's own §18 requires coverage for."""
    service = _service()
    result = service.resolve("We upgraded our it infrastructure last quarter.")

    assert result.confidence_tier == ConfidenceTier.UNRESOLVED
    assert result.primary is None


def test_resolve_ticker_uppercase_word_boundary_does_match() -> None:
    service = _service()
    result = service.resolve(
        "IT shares gained after the earnings call.",
        EntityResolutionContext(title="IT shares gained after the earnings call"),
    )

    assert result.primary is not None
    assert result.primary.entity_id == "initech"


def test_resolve_unrelated_text_is_unresolved() -> None:
    """§18 regression test 2: an unrelated company name must not be
    falsely resolved."""
    service = _service()
    result = service.resolve("The weather today is sunny with a light breeze.")

    assert result.confidence_tier == ConfidenceTier.UNRESOLVED
    assert result.primary is None
    assert result.candidates == ()


def test_resolve_empty_text_is_unresolved_and_never_raises() -> None:
    service = _service()
    result = service.resolve("")

    assert result.confidence_tier == ConfidenceTier.UNRESOLVED
    assert result.primary is None


def test_resolve_is_safe_on_malformed_or_adversarial_text() -> None:
    """Never raises, regardless of input content — including regex
    metacharacters, since candidate terms are `re.escape`d before being
    compiled into a pattern."""
    service = _service()
    adversarial = "((()))[[$^.*+?{}\\|]] Acme \x00\x01 \n\t unicode: café — ünïcödé"

    result = service.resolve(adversarial, EntityResolutionContext(title=adversarial))

    assert result.primary is not None
    assert result.primary.entity_id == "acme"


def test_resolve_title_mention_scores_higher_than_body_only_mention() -> None:
    service = _service()
    body_only = service.resolve("Acme reported earnings.", EntityResolutionContext(title="Markets rally on Fed news"))
    in_title = service.resolve("Acme reported earnings.", EntityResolutionContext(title="Acme reported earnings"))

    assert in_title.primary is not None
    assert body_only.primary is not None
    assert in_title.primary.score > body_only.primary.score
    assert in_title.primary.title_match is True
    assert body_only.primary.title_match is False


def test_resolve_repeated_occurrences_increase_score_but_are_capped() -> None:
    service = _service()
    single = service.resolve("Acme reported strong earnings this quarter.")
    repeated = service.resolve(
        "Acme reported strong earnings. Acme also announced Acme Acme Acme Acme Acme expansion plans."
    )

    assert single.primary is not None
    assert repeated.primary is not None
    assert repeated.primary.score >= single.primary.score
    assert repeated.primary.score <= 1.0


# --- Ambiguity / false-positive prevention (§6, §18) -----------------------


def test_resolve_ambiguous_two_companies_is_medium_not_high() -> None:
    """§18 regression test 3: an ambiguous company remains unresolved/
    medium-confidence rather than being guessed as HIGH."""
    service = _service()
    result = service.resolve(
        "Acme and Globex both announced new products at similar events this week.",
        EntityResolutionContext(title="Acme and Globex both announced new products"),
    )

    assert result.confidence_tier == ConfidenceTier.MEDIUM
    assert len(result.candidates) == 2
    assert {candidate.entity_id for candidate in result.candidates} == {"acme", "globex"}


def test_resolve_ambiguous_result_never_silently_picks_a_winner_as_high() -> None:
    service = _service()
    result = service.resolve(
        "Acme Corporation and Globex Corporation both announced new products.",
        EntityResolutionContext(title="Acme Corporation and Globex Corporation both announced new products"),
    )

    assert result.confidence_tier != ConfidenceTier.HIGH


def test_resolve_secondary_only_includes_candidates_at_or_above_medium_threshold() -> None:
    service = _service(medium_threshold=0.6)
    result = service.resolve(
        "Acme Corporation is the main subject, with a brief unrelated mention of it later.",
        EntityResolutionContext(title="Acme Corporation is the main subject"),
    )

    assert all(candidate.score >= 0.6 for candidate in result.secondary)


def test_resolve_max_candidates_caps_returned_candidates() -> None:
    service = _service(max_candidates=1)
    result = service.resolve(
        "Acme and Globex and Initech (IT) all reported earnings today.",
        EntityResolutionContext(title="Acme and Globex and IT all reported earnings today"),
    )

    assert len(result.candidates) <= 1


# --- Normalization: casing / punctuation / corporate-suffix tolerance ------


def test_resolve_is_case_insensitive_for_names_and_aliases() -> None:
    service = _service()
    result = service.resolve("acme corporation reported earnings.", EntityResolutionContext(title="acme corporation reported earnings"))

    assert result.primary is not None
    assert result.primary.entity_id == "acme"


def test_resolve_tolerates_possessive_punctuation_immediately_after_the_name() -> None:
    """A real-world case (Milestone 11's own live RSS data): "Dell's
    stock..." — the alias must still match with a possessive `'s`
    (or a curly Unicode apostrophe) directly appended, no space."""
    service = _service()
    result = service.resolve("Acme's stock rallied on strong earnings.", EntityResolutionContext(title="Acme’s stock rallied on strong earnings"))

    assert result.primary is not None
    assert result.primary.entity_id == "acme"


def test_resolve_matches_a_suffix_variant_not_in_the_reference_set_via_alias() -> None:
    """§4's "common corporate suffix normalization": the canonical name
    is "Acme Corporation" (no comma) and the alias is "Acme" — text using
    a different real-world suffix variant ("Acme Corp.") still resolves,
    because the suffix-free alias matches as a substring at a word
    boundary, without needing every possible suffix spelled out."""
    service = _service()
    result = service.resolve("Acme Corp. shares rose today.", EntityResolutionContext(title="Acme Corp. shares rose today"))

    assert result.primary is not None
    assert result.primary.entity_id == "acme"


# --- Confidence tier / threshold behavior -----------------------------------


def test_confidence_tier_low_when_below_medium_threshold() -> None:
    service = _service(medium_threshold=0.99, high_threshold=0.995)
    result = service.resolve("Acme reported earnings.", EntityResolutionContext(title="market update"))

    assert result.confidence_tier == ConfidenceTier.LOW
    assert result.primary is None


def test_result_is_explainable_with_reason_and_matched_terms() -> None:
    service = _service()
    result = service.resolve("Acme Corporation reported earnings.", EntityResolutionContext(title="Acme Corporation reported earnings"))

    assert result.reason
    assert result.primary is not None
    assert result.primary.matched_terms


# --- Constructor validation --------------------------------------------


def test_constructor_rejects_medium_threshold_above_high_threshold() -> None:
    try:
        EntityResolutionService(_references(), high_threshold=0.5, medium_threshold=0.9)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_constructor_rejects_max_candidates_below_one() -> None:
    try:
        EntityResolutionService(_references(), max_candidates=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


# --- get_by_entity_id() / list_references() (Milestone 13) -----------------


def test_get_by_entity_id_returns_the_matching_reference() -> None:
    service = _service()
    reference = service.get_by_entity_id("acme")
    assert reference is not None
    assert reference.canonical_name == "Acme Corporation"


def test_get_by_entity_id_unknown_id_returns_none() -> None:
    service = _service()
    assert service.get_by_entity_id("does-not-exist") is None


def test_list_references_returns_every_reference() -> None:
    service = _service()
    references = service.list_references()
    assert {reference.entity_id for reference in references} == {"acme", "globex", "initech"}


# --- lookup_by_name_or_ticker(): direct identifier lookup -------------------


def test_lookup_by_exact_canonical_name() -> None:
    service = _service()
    reference = service.lookup_by_name_or_ticker("Acme Corporation", None)

    assert reference is not None
    assert reference.entity_id == "acme"


def test_lookup_by_partial_name_substring() -> None:
    service = _service()
    reference = service.lookup_by_name_or_ticker("Acme", None)

    assert reference is not None
    assert reference.entity_id == "acme"


def test_lookup_by_ticker_case_insensitive() -> None:
    service = _service()
    reference = service.lookup_by_name_or_ticker(None, "acme")

    assert reference is not None
    assert reference.entity_id == "acme"


def test_lookup_unknown_name_and_ticker_returns_none() -> None:
    service = _service()

    assert service.lookup_by_name_or_ticker("Definitely Not A Real Company", "ZZZZ") is None


def test_lookup_with_no_name_or_ticker_returns_none() -> None:
    service = _service()

    assert service.lookup_by_name_or_ticker(None, None) is None


# --- Security (§17): untrusted text is treated as inert data only ----------


def test_resolve_treats_html_and_script_content_as_plain_text_never_executed() -> None:
    """This service never renders, evaluates, or interprets text as
    HTML/JS/SQL — it only runs read-only regex matching over it. A
    record whose title/summary contains a script tag or SQL-like string
    (plausible untrusted RSS content) is scanned exactly like any other
    text and produces no different behavior."""
    service = _service()
    malicious = "<script>alert('x')</script> Acme Corporation'; DROP TABLE users; --"

    result = service.resolve(malicious, EntityResolutionContext(title=malicious))

    assert result.primary is not None
    assert result.primary.entity_id == "acme"
    # The matched term is exactly the literal name text, not anything
    # derived from interpreting the surrounding markup/SQL as code.
    assert "Acme Corporation" in result.primary.matched_terms
