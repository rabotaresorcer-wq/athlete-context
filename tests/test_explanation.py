"""Deterministic tests for the Layer 7 plain-language explanation service."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from athlete_context.analytics import (
    PerformanceDelta,
    ProgressionPoint,
    StandardGap,
)
from athlete_context.competition import PlannedCompetition
from athlete_context.domain import (
    Competition,
    HistoricalResult,
    HistoricalResultStatus,
    PoolLength,
    ProfessionalFeedback,
    RoundType,
    Source,
    SourceType,
    StandardStatus,
    Stroke,
    VerificationStatus,
)
from athlete_context.explanation import (
    AnalyticsExplanationContext,
    CompetitionExplanationContext,
    ExplanationContext,
    ExplanationStatus,
    ExplanationType,
    generate_explanation,
)
from athlete_context.input_processing import LanguageCode

NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
SOURCE_ID = UUID("91000000-0000-0000-0000-000000000001")
ATHLETE_ID = UUID("91000000-0000-0000-0000-000000000002")
COMPETITION_ID = UUID("91000000-0000-0000-0000-000000000003")
EVENT_ID = UUID("91000000-0000-0000-0000-000000000004")
RESULT_ID = UUID("91000000-0000-0000-0000-000000000005")
PREVIOUS_RESULT_ID = UUID("91000000-0000-0000-0000-000000000006")


def make_source() -> Source:
    return Source(
        id=SOURCE_ID,
        original_source="Synthetic official result source",
        source_type=SourceType.OFFICIAL_FEDERATION_RESULT,
        captured_at=NOW,
        original_language="en",
        source_reference="source:synthetic-result",
        source_url="https://example.test/results/synthetic",
        verification_status=VerificationStatus.VERIFIED,
        created_at=NOW,
        updated_at=NOW,
    )


def make_result(
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
) -> HistoricalResult:
    return HistoricalResult(
        id=RESULT_ID,
        athlete_id=ATHLETE_ID,
        competition_id=COMPETITION_ID,
        event_id=EVENT_ID,
        swim_date=date(2026, 8, 20),
        round=RoundType.FINAL,
        distance_m=100,
        stroke=Stroke.FREESTYLE,
        pool_length=PoolLength.LCM_50M,
        official_time_raw="59.50",
        official_time_centiseconds=5950,
        standard_status=StandardStatus.UNKNOWN,
        result_status=HistoricalResultStatus.OFFICIAL,
        verification_status=verification_status,
        source_id=SOURCE_ID,
        source_ids=[SOURCE_ID],
        created_at=NOW,
        updated_at=NOW,
    )


def make_result_context(
    *,
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
    result_verification: VerificationStatus = VerificationStatus.VERIFIED,
    professional_feedback: list[ProfessionalFeedback] | None = None,
) -> ExplanationContext:
    return ExplanationContext(
        explanation_type=ExplanationType.RESULT_SUMMARY,
        athlete_id=ATHLETE_ID,
        result_id=RESULT_ID,
        competition_id=COMPETITION_ID,
        event_id=EVENT_ID,
        historical_result=make_result(result_verification),
        source_provenance=[make_source()],
        verification_status=verification_status,
        professional_feedback=professional_feedback or [],
        language=LanguageCode.EN,
    )


def test_verified_result_explanation() -> None:
    result = generate_explanation(make_result_context(), LanguageCode.EN)

    assert result.status == ExplanationStatus.AVAILABLE
    assert result.explanation_type == ExplanationType.RESULT_SUMMARY
    assert result.summary == (
        "The official result was 59.50 for 100 m freestyle in a 50 m pool."
    )
    assert "verified" in result.verification_note.casefold()
    assert result.supporting_facts[0].verification_status == (
        VerificationStatus.VERIFIED
    )


def test_progression_explanation_uses_precomputed_delta() -> None:
    delta = PerformanceDelta(
        available=True,
        target_result_id=RESULT_ID,
        comparison_result_id=PREVIOUS_RESULT_ID,
        delta_centiseconds=-42,
        delta_percent=Decimal("-0.7000"),
    )
    context = ExplanationContext(
        explanation_type=ExplanationType.PROGRESSION_SUMMARY,
        athlete_id=ATHLETE_ID,
        result_id=RESULT_ID,
        historical_result=make_result(),
        analytics=AnalyticsExplanationContext(
            progression=[
                ProgressionPoint(
                    result_id=PREVIOUS_RESULT_ID,
                    date=date(2026, 7, 20),
                    official_time_centiseconds=5992,
                    competition_id=COMPETITION_ID,
                    source_id=SOURCE_ID,
                )
            ],
            delta_to_previous=delta,
        ),
        source_provenance=[make_source()],
        verification_status=VerificationStatus.VERIFIED,
        language=LanguageCode.EN,
    )

    explanation = generate_explanation(context, LanguageCode.EN)

    assert explanation.explanation_type == ExplanationType.PROGRESSION_SUMMARY
    assert explanation.summary == (
        "Compared with the previous comparable result, this was 0.42 seconds faster."
    )


def test_standard_passed_context() -> None:
    gap = StandardGap(
        available=True,
        result_id=RESULT_ID,
        standard_id=UUID("91000000-0000-0000-0000-000000000007"),
        result_time_centiseconds=5950,
        standard_time_centiseconds=6050,
        gap_centiseconds=-100,
        gap_percent=Decimal("-1.6529"),
        passed=True,
    )
    context = ExplanationContext(
        explanation_type=ExplanationType.STANDARD_CONTEXT,
        result_id=RESULT_ID,
        historical_result=make_result(),
        standard_context=gap,
        source_provenance=[make_source()],
        verification_status=VerificationStatus.VERIFIED,
    )

    explanation = generate_explanation(context, LanguageCode.EN)

    assert explanation.summary == (
        "The result met the supplied standard by 1.00 seconds."
    )


def test_standard_not_passed_context() -> None:
    gap = StandardGap(
        available=True,
        result_id=RESULT_ID,
        standard_id=UUID("91000000-0000-0000-0000-000000000008"),
        result_time_centiseconds=5950,
        standard_time_centiseconds=5850,
        gap_centiseconds=100,
        gap_percent=Decimal("1.7094"),
        passed=False,
    )
    context = ExplanationContext(
        explanation_type=ExplanationType.STANDARD_CONTEXT,
        historical_result=make_result(),
        standard_context=gap,
        verification_status=VerificationStatus.VERIFIED,
    )

    explanation = generate_explanation(context, LanguageCode.EN)

    assert explanation.summary == (
        "The result was 1.00 seconds outside the supplied standard."
    )


def test_unverified_result_is_clearly_labelled() -> None:
    context = make_result_context(
        result_verification=VerificationStatus.UNVERIFIED
    )

    explanation = generate_explanation(context, LanguageCode.EN)

    assert explanation.summary.startswith("An unverified result record reports")
    assert "unverified" in explanation.verification_note.casefold()
    assert explanation.supporting_facts[0].verification_status == (
        VerificationStatus.UNVERIFIED
    )


def test_conflict_is_not_silently_resolved() -> None:
    context = make_result_context(
        verification_status=VerificationStatus.CONFLICT,
    ).model_copy(update={"unresolved_items": ["official sources disagree"]})

    explanation = generate_explanation(context, LanguageCode.EN)

    assert explanation.explanation_type == ExplanationType.CONFLICT_NOTICE
    assert "conflict" in explanation.summary.casefold()
    assert explanation.unresolved_items == ["official sources disagree"]


def test_conflicting_identifiers_produce_conflict_notice() -> None:
    context = make_result_context().model_copy(
        update={
            "competition_id": UUID("91000000-0000-0000-0000-000000000099")
        }
    )

    explanation = generate_explanation(context, LanguageCode.EN)

    assert explanation.explanation_type == ExplanationType.CONFLICT_NOTICE
    assert "conflicting competition_id" in explanation.unresolved_items


def test_unknown_context_is_handled_safely() -> None:
    context = ExplanationContext(
        explanation_type=ExplanationType.RESULT_SUMMARY,
        verification_status=VerificationStatus.UNKNOWN,
        language=LanguageCode.UNKNOWN,
    )

    explanation = generate_explanation(context, LanguageCode.EN)

    assert explanation.explanation_type == ExplanationType.INSUFFICIENT_CONTEXT
    assert "not enough verified context" in explanation.summary
    assert "historical result is unavailable" in explanation.unresolved_items


def test_missing_analytics_is_handled_safely() -> None:
    context = ExplanationContext(
        explanation_type=ExplanationType.PROGRESSION_SUMMARY,
        historical_result=make_result(),
        verification_status=VerificationStatus.VERIFIED,
    )

    explanation = generate_explanation(context, LanguageCode.EN)

    assert explanation.explanation_type == ExplanationType.INSUFFICIENT_CONTEXT
    assert "analytics are unavailable" in explanation.unresolved_items


def test_source_provenance_is_preserved() -> None:
    explanation = generate_explanation(make_result_context(), LanguageCode.EN)

    assert len(explanation.source_references) == 1
    reference = explanation.source_references[0]
    assert reference.source_id == SOURCE_ID
    assert reference.original_source == "Synthetic official result source"
    assert reference.source_reference == "source:synthetic-result"
    assert reference.source_url == "https://example.test/results/synthetic"
    assert explanation.supporting_facts[0].source_ids == [SOURCE_ID]


def test_professional_feedback_does_not_become_verified_result() -> None:
    feedback = ProfessionalFeedback(
        id=UUID("91000000-0000-0000-0000-000000000009"),
        source_id=UUID("91000000-0000-0000-0000-000000000010"),
        original_language="en",
        verification_status=VerificationStatus.VERIFIED,
        athlete_id=ATHLETE_ID,
        professional_name="Synthetic Professional",
        professional_role="coach",
        content="The athlete should change training immediately.",
        provided_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    context = make_result_context(professional_feedback=[feedback])

    explanation = generate_explanation(context, LanguageCode.EN)

    feedback_fact = explanation.supporting_facts[-1]
    assert feedback_fact.verification_status == VerificationStatus.UNVERIFIED
    assert "unverified context" in feedback_fact.text
    assert feedback.content not in feedback_fact.text


def test_russian_output() -> None:
    explanation = generate_explanation(make_result_context(), LanguageCode.RU)

    assert explanation.language == LanguageCode.RU
    assert explanation.summary.startswith("Официальный результат")
    assert "проверенного" not in explanation.summary.casefold()


def test_english_output() -> None:
    explanation = generate_explanation(make_result_context(), LanguageCode.EN)

    assert explanation.language == LanguageCode.EN
    assert explanation.summary.startswith("The official result")


def test_output_contains_no_coaching_recommendation_language() -> None:
    feedback = ProfessionalFeedback(
        id=UUID("91000000-0000-0000-0000-000000000011"),
        source_id=UUID("91000000-0000-0000-0000-000000000012"),
        original_language="en",
        athlete_id=ATHLETE_ID,
        professional_name="Synthetic Professional",
        content="The coach should prescribe a different training plan.",
        provided_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    explanation = generate_explanation(
        make_result_context(professional_feedback=[feedback]),
        LanguageCode.EN,
    )
    rendered = " ".join(
        [explanation.summary or ""]
        + [fact.text for fact in explanation.supporting_facts]
    ).casefold()

    assert "should" not in rendered
    assert "training plan" not in rendered
    assert "coach should" not in rendered


def test_competition_update_contains_no_competition_recommendation() -> None:
    competition = Competition(
        id=COMPETITION_ID,
        name="Synthetic Approved Competition",
        start_date=date(2026, 10, 1),
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[SOURCE_ID],
        created_at=NOW,
        updated_at=NOW,
    )
    plan = PlannedCompetition(
        competition=competition,
        approved=True,
        created_at=NOW,
        updated_at=NOW,
    )
    context = ExplanationContext(
        explanation_type=ExplanationType.COMPETITION_UPDATE,
        competition_id=COMPETITION_ID,
        competition_context=CompetitionExplanationContext(
            planned_competition=plan
        ),
        source_provenance=[make_source()],
        verification_status=VerificationStatus.VERIFIED,
    )

    explanation = generate_explanation(context, LanguageCode.EN)
    rendered = explanation.summary.casefold()

    assert "recommend" not in rendered
    assert "should" not in rendered
    assert "select" not in rendered


def test_unsupported_output_language_is_structurally_unavailable() -> None:
    explanation = generate_explanation(make_result_context(), LanguageCode.TR)

    assert explanation.status == ExplanationStatus.UNAVAILABLE
    assert explanation.summary is None
    assert explanation.language == LanguageCode.TR
    assert explanation.unresolved_items == ["unsupported output language: TR"]


def test_repeated_generation_is_deterministic() -> None:
    context = make_result_context()

    first = generate_explanation(context, LanguageCode.EN)
    second = generate_explanation(context, LanguageCode.EN)

    assert first == second
    assert first.model_dump() == second.model_dump()
