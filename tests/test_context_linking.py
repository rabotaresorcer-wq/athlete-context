"""Deterministic tests for the Layer 5 Context Linking service."""

from datetime import datetime, timezone
from uuid import UUID

from athlete_context.context_linking import (
    ContextLinkingService,
    EntityType,
    ExactReference,
    InMemoryContextRepository,
    LinkStatus,
    RecordType,
    link_context,
)
from athlete_context.domain import (
    Athlete,
    Competition,
    Event,
    VerificationStatus,
)
from athlete_context.input_processing import (
    ContentType,
    DeterministicTranslator,
    InputProcessingService,
    LanguageCode,
    NormalizedInput,
    RawInput,
)

NOW = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
SOURCE_ID = UUID("71000000-0000-0000-0000-000000000001")
INPUT_ID = UUID("71000000-0000-0000-0000-000000000002")
ATHLETE_ID = UUID("71000000-0000-0000-0000-000000000010")
COMPETITION_ID = UUID("71000000-0000-0000-0000-000000000020")
OTHER_COMPETITION_ID = UUID("71000000-0000-0000-0000-000000000021")
EVENT_ID = UUID("71000000-0000-0000-0000-000000000030")
OTHER_EVENT_ID = UUID("71000000-0000-0000-0000-000000000031")


def make_repository(*, ambiguous_reference: bool = False) -> InMemoryContextRepository:
    athlete = Athlete(
        id=ATHLETE_ID,
        display_name="Synthetic Athlete",
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[SOURCE_ID],
        created_at=NOW,
        updated_at=NOW,
    )
    competition = Competition(
        id=COMPETITION_ID,
        name="Synthetic Competition",
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[SOURCE_ID],
        created_at=NOW,
        updated_at=NOW,
    )
    other_competition = Competition(
        id=OTHER_COMPETITION_ID,
        name="Other Synthetic Competition",
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[SOURCE_ID],
        created_at=NOW,
        updated_at=NOW,
    )
    event = Event(
        id=EVENT_ID,
        competition_id=COMPETITION_ID,
        name="Synthetic Event",
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[SOURCE_ID],
        created_at=NOW,
        updated_at=NOW,
    )
    other_event = Event(
        id=OTHER_EVENT_ID,
        competition_id=OTHER_COMPETITION_ID,
        name="Other Synthetic Event",
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[SOURCE_ID],
        created_at=NOW,
        updated_at=NOW,
    )
    references = [
        ExactReference(
            entity_type=EntityType.ATHLETE,
            reference="athlete:synthetic",
            entity_id=ATHLETE_ID,
        ),
        ExactReference(
            entity_type=EntityType.COMPETITION,
            reference="competition:primary",
            entity_id=COMPETITION_ID,
        ),
        ExactReference(
            entity_type=EntityType.COMPETITION,
            reference="competition:other",
            entity_id=OTHER_COMPETITION_ID,
        ),
        ExactReference(
            entity_type=EntityType.EVENT,
            reference="event:primary",
            entity_id=EVENT_ID,
        ),
    ]
    if ambiguous_reference:
        references.extend(
            [
                ExactReference(
                    entity_type=EntityType.COMPETITION,
                    reference="competition:ambiguous",
                    entity_id=COMPETITION_ID,
                ),
                ExactReference(
                    entity_type=EntityType.COMPETITION,
                    reference="competition:ambiguous",
                    entity_id=OTHER_COMPETITION_ID,
                ),
            ]
        )
    return InMemoryContextRepository(
        athletes=[athlete],
        competitions=[competition, other_competition],
        events=[event, other_event],
        exact_references=references,
    )


def make_normalized(
    structured_data: dict[str, object],
    *,
    content_type: ContentType = ContentType.STRUCTURED_DATA,
    raw_text: str | None = None,
    translator: DeterministicTranslator | None = None,
) -> NormalizedInput:
    raw_input = RawInput(
        id=INPUT_ID,
        source_id=SOURCE_ID,
        content_type=content_type,
        raw_text=raw_text,
        structured_data=structured_data,
        captured_at=NOW,
    )
    return InputProcessingService(translator).process_input(raw_input)


def full_result_data() -> dict[str, object]:
    return {
        "record_type": "RESULT",
        "athlete_id": str(ATHLETE_ID),
        "competition_id": str(COMPETITION_ID),
        "event_id": str(EVENT_ID),
    }


def test_exact_athlete_match() -> None:
    normalized = make_normalized(
        {"record_type": "RESULT", "athlete_id": str(ATHLETE_ID)}
    )

    result = ContextLinkingService().link_context(normalized, make_repository())

    assert result.athlete_id == ATHLETE_ID
    assert result.matched_references["athlete_id"] == ATHLETE_ID


def test_exact_competition_match() -> None:
    normalized = make_normalized(
        {"record_type": "DOCUMENT", "competition_id": str(COMPETITION_ID)}
    )

    result = ContextLinkingService().link_context(normalized, make_repository())

    assert result.competition_id == COMPETITION_ID
    assert result.link_status == LinkStatus.LINKED


def test_exact_event_reference_match() -> None:
    normalized = make_normalized(
        {"record_type": "STANDARD", "event_reference": "event:primary"}
    )

    result = ContextLinkingService().link_context(normalized, make_repository())

    assert result.event_id == EVENT_ID
    assert result.matched_references["event_reference"] == EVENT_ID
    assert result.link_status == LinkStatus.LINKED


def test_fully_linked_result() -> None:
    result = link_context(make_normalized(full_result_data()), make_repository())

    assert result.record_type == RecordType.RESULT
    assert result.athlete_id == ATHLETE_ID
    assert result.competition_id == COMPETITION_ID
    assert result.event_id == EVENT_ID
    assert result.link_status == LinkStatus.LINKED


def test_athlete_only_reference_is_partially_linked() -> None:
    normalized = make_normalized(
        {
            "record_type": "RESULT",
            "athlete_reference": "athlete:synthetic",
        }
    )

    result = link_context(normalized, make_repository())

    assert result.athlete_id == ATHLETE_ID
    assert result.link_status == LinkStatus.PARTIALLY_LINKED
    assert "competition_id" in result.unresolved_references
    assert "event_id" in result.unresolved_references


def test_missing_competition_remains_unresolved() -> None:
    normalized = make_normalized(
        {
            "record_type": "RESULT",
            "athlete_id": str(ATHLETE_ID),
            "event_id": str(EVENT_ID),
        }
    )

    result = link_context(normalized, make_repository())

    assert result.link_status == LinkStatus.PARTIALLY_LINKED
    assert result.competition_id is None
    assert result.unresolved_references["competition_id"] == (
        "missing explicit competition reference"
    )


def test_unknown_event_remains_unresolved() -> None:
    unknown_event_id = UUID("71000000-0000-0000-0000-000000000099")
    normalized = make_normalized(
        {
            "record_type": "RESULT",
            "athlete_id": str(ATHLETE_ID),
            "competition_id": str(COMPETITION_ID),
            "event_id": str(unknown_event_id),
        }
    )

    result = link_context(normalized, make_repository())

    assert result.event_id is None
    assert result.link_status == LinkStatus.PARTIALLY_LINKED
    assert result.unresolved_references["event_id"] == "no exact entity match"


def test_ambiguous_competition_reference_is_conflict() -> None:
    normalized = make_normalized(
        {
            "record_type": "RESULT",
            "athlete_id": str(ATHLETE_ID),
            "competition_reference": "competition:ambiguous",
            "event_id": str(EVENT_ID),
        }
    )

    result = link_context(
        normalized,
        make_repository(ambiguous_reference=True),
    )

    assert result.link_status == LinkStatus.CONFLICT
    assert result.verification_status == VerificationStatus.CONFLICT
    assert result.competition_id is None


def test_incompatible_explicit_references_are_conflict() -> None:
    normalized = make_normalized(
        {
            "record_type": "RESULT",
            "athlete_id": str(ATHLETE_ID),
            "competition_id": str(COMPETITION_ID),
            "competition_reference": "competition:other",
            "event_id": str(EVENT_ID),
        }
    )

    result = link_context(normalized, make_repository())

    assert result.link_status == LinkStatus.CONFLICT
    assert result.competition_id is None
    assert result.unresolved_references["competition"] == (
        "incompatible explicit references"
    )


def test_event_and_competition_relationship_conflict() -> None:
    normalized = make_normalized(
        {
            "record_type": "RESULT",
            "athlete_id": str(ATHLETE_ID),
            "competition_id": str(COMPETITION_ID),
            "event_id": str(OTHER_EVENT_ID),
        }
    )

    result = link_context(normalized, make_repository())

    assert result.link_status == LinkStatus.CONFLICT
    assert result.unresolved_references["event_competition"] == (
        "event belongs to a different competition"
    )


def test_unknown_record_type_is_unresolved() -> None:
    normalized = make_normalized(
        {"record_type": "UNSUPPORTED", "athlete_id": str(ATHLETE_ID)}
    )

    result = link_context(normalized, make_repository())

    assert result.record_type == RecordType.UNKNOWN
    assert result.link_status == LinkStatus.UNRESOLVED
    assert "record_type" in result.unresolved_references


def test_provenance_and_structured_input_are_preserved() -> None:
    data = full_result_data()
    normalized = make_normalized(data)

    result = link_context(normalized, make_repository())

    assert result.input_id == INPUT_ID
    assert result.source_id == SOURCE_ID
    assert result.captured_at == NOW
    assert result.structured_data == data


def test_original_and_translated_text_are_preserved() -> None:
    original = "The result is official"
    translated = "Результат официальный"
    translator = DeterministicTranslator(
        {(original, LanguageCode.EN, LanguageCode.RU): translated}
    )
    normalized = make_normalized(
        {"athlete_id": str(ATHLETE_ID)},
        content_type=ContentType.MESSAGE,
        raw_text=original,
        translator=translator,
    )

    result = link_context(normalized, make_repository())

    assert result.original_text == original
    assert result.translated_text == translated
    assert result.original_text != result.translated_text


def test_linked_message_remains_unverified() -> None:
    normalized = make_normalized(
        {"athlete_id": str(ATHLETE_ID)},
        content_type=ContentType.MESSAGE,
        raw_text="Message about a known athlete",
    )

    result = link_context(normalized, make_repository())

    assert result.record_type == RecordType.MESSAGE
    assert result.link_status == LinkStatus.LINKED
    assert result.verification_status == VerificationStatus.UNVERIFIED


def test_free_text_does_not_trigger_entity_guessing() -> None:
    raw_input = RawInput(
        id=INPUT_ID,
        source_id=SOURCE_ID,
        content_type=ContentType.MESSAGE,
        raw_text=(
            f"Possible athlete {ATHLETE_ID}, competition {COMPETITION_ID}, "
            f"event {EVENT_ID}"
        ),
        captured_at=NOW,
    )
    normalized = InputProcessingService().process_input(raw_input)

    result = link_context(normalized, make_repository())

    assert result.link_status == LinkStatus.UNRESOLVED
    assert result.athlete_id is None
    assert result.competition_id is None
    assert result.event_id is None


def test_repeated_linking_is_deterministic() -> None:
    normalized = make_normalized(full_result_data())
    repository = make_repository()
    service = ContextLinkingService()

    first = service.link_context(normalized, repository)
    second = service.link_context(normalized, repository)

    assert first == second
    assert first.model_dump() == second.model_dump()


def test_structured_explicit_ids_link_without_conversion_to_domain_records() -> None:
    normalized = make_normalized(full_result_data())

    result = link_context(normalized, make_repository())

    assert result.matched_references == {
        "athlete_id": ATHLETE_ID,
        "competition_id": COMPETITION_ID,
        "event_id": EVENT_ID,
    }
    assert normalized.structured_data == full_result_data()
