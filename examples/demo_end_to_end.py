"""Deterministic synthetic end-to-end demonstration of Athlete Context Layers 1–7."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import UUID

from athlete_context import (
    AnalyticsExplanationContext,
    Athlete,
    Competition,
    ContextLinkingService,
    DeterministicTranslator,
    Event,
    ExactReference,
    ExplanationContext,
    ExplanationType,
    FederationUpdateType,
    HistoricalPerformanceAnalytics,
    HistoricalResultIngestService,
    HistoricalResultStatus,
    InMemoryContextRepository,
    InMemoryHistoricalResultRepository,
    InputProcessingService,
    LanguageCode,
    MonitoredFederationUpdate,
    PlannedCompetition,
    PoolLength,
    RawInput,
    RecordType,
    RoundType,
    Source,
    SourceType,
    StandardStatus,
    Stroke,
    StructuredHistoricalResultInput,
    VerificationStatus,
    advance_competition_lifecycle,
    create_monitoring_plan,
    generate_explanation,
    record_monitoring_update,
)
from athlete_context.context_linking import EntityType
from athlete_context.input_processing import ContentType

DEMO_TIME = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
ATHLETE_ID = UUID("a1000000-0000-0000-0000-000000000001")
COMPETITION_ID = UUID("a2000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("a3000000-0000-0000-0000-000000000001")
MESSAGE_SOURCE_ID = UUID("a4000000-0000-0000-0000-000000000001")
RAW_INPUT_ID = UUID("a5000000-0000-0000-0000-000000000001")
TURKISH_MESSAGE = "Sentetik sporcu 50 metre serbest yarışını 29.60 ile tamamladı."
RUSSIAN_TRANSLATION = (
    "Синтетический спортсмен завершил заплыв на 50 метров вольным стилем "
    "с результатом 29.60."
)


class DeterministicIdFactory:
    """Return fixed record IDs so repeated demo runs produce identical output."""

    def __init__(self) -> None:
        self._next = 1

    def __call__(self) -> UUID:
        value = UUID(f"a6000000-0000-0000-0000-{self._next:012d}")
        self._next += 1
        return value


def _source(number: int, *, pool: PoolLength) -> Source:
    source_id = UUID(f"a7000000-0000-0000-0000-{number:012d}")
    return Source(
        id=source_id,
        original_source=f"Synthetic official {pool.value} result source {number}",
        source_type=SourceType.OFFICIAL_COMPETITION_SYSTEM,
        captured_at=DEMO_TIME,
        original_language="tr",
        source_reference=f"synthetic-result:{number}",
        source_url=f"https://example.test/synthetic-results/{number}",
        verification_status=VerificationStatus.VERIFIED,
        created_at=DEMO_TIME,
        updated_at=DEMO_TIME,
    )


def _structured_result(
    source: Source,
    *,
    swim_date: date,
    raw_time: str,
    pool: PoolLength,
) -> StructuredHistoricalResultInput:
    return StructuredHistoricalResultInput(
        athlete_id=ATHLETE_ID,
        competition_id=COMPETITION_ID,
        event_id=EVENT_ID,
        swim_date=swim_date,
        round=RoundType.FINAL,
        heat_number=1,
        lane=4,
        distance_m=50,
        stroke=Stroke.FREESTYLE,
        pool_length=pool,
        official_time_raw=raw_time,
        standard_status=StandardStatus.UNKNOWN,
        result_status=HistoricalResultStatus.OFFICIAL,
        verification_status=VerificationStatus.VERIFIED,
        source_id=source.id,
    )


def run_demo() -> dict[str, object]:
    """Run one complete in-memory scenario and return readable primitive output."""

    result_sources = {
        "first_lcm": _source(1, pool=PoolLength.LCM_50M),
        "scm_control": _source(2, pool=PoolLength.SCM_25M),
        "previous_lcm": _source(3, pool=PoolLength.LCM_50M),
        "new_lcm": _source(4, pool=PoolLength.LCM_50M),
    }
    identity_source = result_sources["first_lcm"]
    athlete = Athlete(
        id=ATHLETE_ID,
        display_name="Synthetic Athlete Northstar",
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[identity_source.id],
        created_at=DEMO_TIME,
        updated_at=DEMO_TIME,
    )
    competition = Competition(
        id=COMPETITION_ID,
        name="Fictional Horizon Swim Series",
        start_date=date(2026, 1, 15),
        end_date=date(2026, 4, 20),
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[identity_source.id],
        created_at=DEMO_TIME,
        updated_at=DEMO_TIME,
    )
    event = Event(
        id=EVENT_ID,
        competition_id=COMPETITION_ID,
        name="Synthetic 50 m freestyle LCM event",
        discipline="50 m freestyle",
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[identity_source.id],
        created_at=DEMO_TIME,
        updated_at=DEMO_TIME,
    )

    message_source = Source(
        id=MESSAGE_SOURCE_ID,
        original_source="Synthetic Turkish message",
        source_type=SourceType.PROFESSIONAL_MESSAGE,
        captured_at=DEMO_TIME,
        original_language="tr",
        source_reference="synthetic-message:1",
        source_url=None,
        verification_status=VerificationStatus.UNVERIFIED,
        created_at=DEMO_TIME,
        updated_at=DEMO_TIME,
    )
    raw_input = RawInput(
        id=RAW_INPUT_ID,
        source_id=message_source.id,
        content_type=ContentType.MESSAGE,
        raw_text=TURKISH_MESSAGE,
        structured_data={
            "record_type": RecordType.RESULT.value,
            "athlete_id": str(ATHLETE_ID),
            "competition_id": str(COMPETITION_ID),
            "event_id": str(EVENT_ID),
            "official_time_raw": "29.60",
        },
        captured_at=DEMO_TIME,
    )
    translator = DeterministicTranslator(
        {
            (
                TURKISH_MESSAGE,
                LanguageCode.TR,
                LanguageCode.RU,
            ): RUSSIAN_TRANSLATION
        }
    )
    normalized = InputProcessingService(translator).process_input(raw_input)

    context_repository = InMemoryContextRepository(
        athletes=[athlete],
        competitions=[competition],
        events=[event],
        exact_references=[
            ExactReference(
                entity_type=EntityType.ATHLETE,
                reference="synthetic-athlete:northstar",
                entity_id=ATHLETE_ID,
            )
        ],
    )
    linked = ContextLinkingService().link_context(normalized, context_repository)

    historical_repository = InMemoryHistoricalResultRepository()
    ingest_service = HistoricalResultIngestService(
        historical_repository,
        clock=lambda: DEMO_TIME,
        id_factory=DeterministicIdFactory(),
    )
    ingest_definitions = (
        (
            "first_lcm",
            date(2026, 1, 20),
            "30.20",
            PoolLength.LCM_50M,
        ),
        (
            "scm_control",
            date(2026, 2, 20),
            "28.00",
            PoolLength.SCM_25M,
        ),
        (
            "previous_lcm",
            date(2026, 3, 20),
            "29.90",
            PoolLength.LCM_50M,
        ),
        (
            "new_lcm",
            date(2026, 4, 20),
            "29.60",
            PoolLength.LCM_50M,
        ),
    )
    outcomes = {}
    for source_name, swim_date, raw_time, pool in ingest_definitions:
        source = result_sources[source_name]
        outcomes[source_name] = ingest_service.ingest(
            _structured_result(
                source,
                swim_date=swim_date,
                raw_time=raw_time,
                pool=pool,
            ),
            source=source,
        )
    new_outcome = outcomes["new_lcm"]
    if new_outcome.record is None:
        raise RuntimeError("synthetic official result was not ingested")
    new_result = new_outcome.record

    analytics = HistoricalPerformanceAnalytics(
        historical_repository.all(),
        sources=result_sources.values(),
    )
    personal_best = analytics.personal_best(new_result)
    delta_to_previous = analytics.delta_to_previous(new_result)
    delta_to_pb = analytics.delta_to_historical_pb(new_result)
    progression = analytics.result_progression(new_result)
    trend = analytics.trend(new_result)
    consistency = analytics.consistency(new_result)
    if delta_to_previous.comparison_result_id is None:
        raise RuntimeError("synthetic previous comparable result is unavailable")
    previous_result = historical_repository.get(
        delta_to_previous.comparison_result_id
    )

    planned_competition = PlannedCompetition(
        competition=competition,
        approved=True,
        federation_source_reference="synthetic-federation:horizon-series",
        created_at=DEMO_TIME,
        updated_at=DEMO_TIME,
    )
    monitoring_plan = create_monitoring_plan(planned_competition)
    result_update = MonitoredFederationUpdate(
        id=UUID("a8000000-0000-0000-0000-000000000001"),
        source_id=result_sources["new_lcm"].id,
        original_language="tr",
        verification_status=VerificationStatus.VERIFIED,
        federation_name="Synthetic Federation",
        title="Synthetic official result publication",
        content="Synthetic result data supplied directly to the demo",
        published_at=DEMO_TIME,
        competition_id=COMPETITION_ID,
        update_type=FederationUpdateType.RESULT,
        captured_at=DEMO_TIME,
        payload={"historical_result_id": str(new_result.id)},
        update_reference="synthetic-federation-update:result-1",
        created_at=DEMO_TIME,
        updated_at=DEMO_TIME,
    )
    monitoring_plan = record_monitoring_update(monitoring_plan, result_update)
    lifecycle = advance_competition_lifecycle(
        planned_competition,
        monitoring_plan,
        DEMO_TIME,
        historical_result=new_result,
        context_link=linked,
    )

    explanation_context = ExplanationContext(
        explanation_type=ExplanationType.PROGRESSION_SUMMARY,
        athlete_id=ATHLETE_ID,
        result_id=new_result.id,
        competition_id=COMPETITION_ID,
        event_id=EVENT_ID,
        historical_result=new_result,
        context_link=linked,
        analytics=AnalyticsExplanationContext(
            progression=list(progression),
            delta_to_previous=delta_to_previous,
            delta_to_historical_pb=delta_to_pb,
            trend=trend,
            consistency=consistency,
        ),
        source_provenance=[result_sources["new_lcm"]],
        verification_status=VerificationStatus.VERIFIED,
        language=LanguageCode.TR,
    )
    explanation = generate_explanation(explanation_context, LanguageCode.RU)

    comparable_ids = {point.result_id for point in progression}
    scm_record = outcomes["scm_control"].record
    if scm_record is None:
        raise RuntimeError("synthetic SCM control result was not ingested")

    return {
        "language_flow": {
            "original_turkish": normalized.original_text,
            "detected_language": normalized.original_language.value,
            "russian_translation": normalized.translated_text,
            "translation_status": normalized.translation_status.value,
            "original_preserved": normalized.original_text == TURKISH_MESSAGE,
        },
        "linking": {
            "status": linked.link_status.value,
            "verification_status": linked.verification_status.value,
            "athlete_id": str(linked.athlete_id),
            "competition_id": str(linked.competition_id),
            "event_id": str(linked.event_id),
            "source_id": str(linked.source_id),
        },
        "official_result": {
            "ingest_status": new_outcome.status.value,
            "result_id": str(new_result.id),
            "time": new_result.official_time_raw,
            "pool_length": new_result.pool_length.value,
            "verification_status": new_result.verification_status.value,
            "source_id": str(new_result.source_id),
        },
        "analytics": {
            "previous_result_id": str(previous_result.id),
            "previous_time": previous_result.official_time_raw,
            "delta_centiseconds": delta_to_previous.delta_centiseconds,
            "delta_percent": str(delta_to_previous.delta_percent),
            "personal_best_result_id": (
                str(personal_best.result_id) if personal_best else None
            ),
            "new_personal_best": delta_to_pb.new_pb,
            "progression_result_ids": [str(point.result_id) for point in progression],
            "trend": trend.status.value,
            "trend_sample_size": trend.sample_size,
            "consistency_status": consistency.status.value,
            "consistency_sample_size": consistency.sample_size,
            "scm_control_time": scm_record.official_time_raw,
            "scm_control_excluded": scm_record.id not in comparable_ids,
        },
        "competition_lifecycle": {
            "explicitly_approved": planned_competition.approved,
            "monitoring_competition_id": str(monitoring_plan.competition_id),
            "monitoring_check_count": len(monitoring_plan.checks),
            "update_type": result_update.update_type.value,
            "update_verification_status": result_update.verification_status.value,
            "lifecycle_status": lifecycle.lifecycle_status.value,
            "live_federation_access": False,
        },
        "provenance": {
            "message_source_id": str(message_source.id),
            "official_result_source_id": str(new_result.source_id),
            "explanation_source_ids": [
                str(reference.source_id)
                for reference in explanation.source_references
            ],
        },
        "final_explanation": {
            "language": explanation.language.value,
            "summary": explanation.summary,
            "verification_note": explanation.verification_note,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
