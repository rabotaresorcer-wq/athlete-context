"""Deterministic tests for Layer 1 domain validation and relationships."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from athlete_context.domain import (
    Athlete,
    Competition,
    Document,
    Event,
    FederationUpdate,
    Message,
    ProfessionalFeedback,
    Result,
    ResultStatus,
    ResultTrace,
    Source,
    SourceType,
    Standard,
    VerificationStatus,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
OTHER_SOURCE_ID = UUID("00000000-0000-0000-0000-000000000091")
OTHER_COMPETITION_ID = UUID("00000000-0000-0000-0000-000000000092")
FEEDBACK_ATHLETE_ID = UUID("00000000-0000-0000-0000-000000000093")


def make_source() -> Source:
    return Source(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        original_source="Official competition results",
        source_type=SourceType.OFFICIAL_RESULT,
        captured_at=NOW,
        original_language="en",
        source_reference="results-2026-001",
        source_url="https://example.test/results/2026-001",
        published_at=NOW - timedelta(hours=1),
        verification_status=VerificationStatus.VERIFIED,
        created_at=NOW,
        updated_at=NOW,
    )


def make_trace() -> ResultTrace:
    source = make_source()
    athlete = Athlete(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        display_name="Example Athlete",
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[source.id],
        created_at=NOW,
        updated_at=NOW,
    )
    competition = Competition(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        name="Example Competition",
        start_date=date(2026, 1, 15),
        end_date=date(2026, 1, 16),
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[source.id],
        created_at=NOW,
        updated_at=NOW,
    )
    event = Event(
        id=UUID("00000000-0000-0000-0000-000000000004"),
        competition_id=competition.id,
        name="Example Event",
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[source.id],
        created_at=NOW,
        updated_at=NOW,
    )
    result = Result(
        id=UUID("00000000-0000-0000-0000-000000000005"),
        athlete_id=athlete.id,
        competition_id=competition.id,
        event_id=event.id,
        source_id=source.id,
        status=ResultStatus.COMPLETED,
        performance_value=Decimal("10.42"),
        performance_unit="seconds",
        placing=1,
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[source.id],
        created_at=NOW,
        updated_at=NOW,
    )
    return ResultTrace(
        athlete=athlete,
        competition=competition,
        event=event,
        source=source,
        result=result,
    )


def test_entity_defaults_use_uuid_and_aware_timestamps() -> None:
    source = make_source()
    athlete = Athlete(
        display_name="Example Athlete",
        verification_status=VerificationStatus.UNKNOWN,
        source_ids=[source.id],
    )

    assert isinstance(athlete.id, UUID)
    assert athlete.created_at.tzinfo is not None
    assert athlete.updated_at >= athlete.created_at


def test_source_requires_complete_explicit_provenance() -> None:
    with pytest.raises(ValidationError):
        Source(
            original_source="Official results",
            source_type=SourceType.OFFICIAL_RESULT,
            captured_at=NOW,
            source_reference=None,
            source_url=None,
            verification_status=VerificationStatus.UNKNOWN,
        )

    source = Source(
        original_source="Offline certificate",
        source_type=SourceType.DOCUMENT,
        captured_at=NOW,
        original_language=None,
        source_reference=None,
        source_url=None,
        verification_status=VerificationStatus.UNKNOWN,
    )
    assert source.original_language is None


def test_factual_records_require_provenance_and_verification() -> None:
    with pytest.raises(ValidationError):
        Athlete(display_name="Missing provenance")

    with pytest.raises(ValidationError):
        Athlete(
            display_name="Empty provenance",
            verification_status=VerificationStatus.UNKNOWN,
            source_ids=[],
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"performance_unit": None}, "provided together"),
        ({"performance_value": Decimal("-1")}, "greater than or equal to 0"),
        ({"source_id": OTHER_SOURCE_ID}, "present in source_ids"),
        ({"placing": 0}, "greater than or equal to 1"),
    ],
)
def test_result_rejects_invalid_values(
    updates: dict[str, object], message: str
) -> None:
    data = make_trace().result.model_dump()
    data.update(updates)

    with pytest.raises(ValidationError, match=message):
        Result.model_validate(data)


def test_result_trace_accepts_complete_relationship_chain() -> None:
    trace = make_trace()

    assert trace.result.athlete_id == trace.athlete.id
    assert trace.result.competition_id == trace.competition.id
    assert trace.result.event_id == trace.event.id
    assert trace.result.source_id == trace.source.id


def test_result_trace_rejects_mismatched_relationship() -> None:
    trace = make_trace()
    wrong_event = trace.event.model_copy(
        update={"competition_id": OTHER_COMPETITION_ID}
    )

    with pytest.raises(ValidationError, match="event does not belong"):
        ResultTrace(
            athlete=trace.athlete,
            competition=trace.competition,
            event=wrong_event,
            source=trace.source,
            result=trace.result,
        )


def test_standard_supports_event_age_category_and_context() -> None:
    trace = make_trace()
    standard = Standard(
        event_id=trace.event.id,
        name="Example qualification standard",
        value=Decimal("10.50"),
        unit="seconds",
        minimum_age=18,
        maximum_age=23,
        category="U23",
        context={"venue": "outdoor"},
        verification_status=VerificationStatus.UNVERIFIED,
        source_ids=[trace.source.id],
        created_at=NOW,
        updated_at=NOW,
    )

    assert standard.event_id == trace.event.id
    assert standard.context == {"venue": "outdoor"}

    with pytest.raises(ValidationError, match="maximum_age"):
        Standard.model_validate(
            standard.model_copy(
                update={"minimum_age": 24, "maximum_age": 18}
            ).model_dump()
        )


@pytest.mark.parametrize(
    "record_factory",
    [
        lambda source_id: Message(
            source_id=source_id,
            original_language="en",
            sender="Coach",
            content="Original message",
            sent_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        ),
        lambda source_id: Document(
            source_id=source_id,
            original_language=None,
            title="Original document",
            storage_reference="document://original/1",
            created_at=NOW,
            updated_at=NOW,
        ),
        lambda source_id: ProfessionalFeedback(
            source_id=source_id,
            original_language="en",
            athlete_id=FEEDBACK_ATHLETE_ID,
            professional_name="Example Coach",
            content="Original feedback",
            provided_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        ),
        lambda source_id: FederationUpdate(
            source_id=source_id,
            original_language="en",
            federation_name="Example Federation",
            title="Original update",
            content="Original publication text",
            created_at=NOW,
            updated_at=NOW,
        ),
    ],
)
def test_source_records_do_not_default_to_verified_facts(record_factory) -> None:
    record = record_factory(make_source().id)

    assert record.verification_status == VerificationStatus.UNVERIFIED
    assert record.verification_scope == "record_authenticity"


def test_invalid_timestamps_and_extra_fields_are_rejected() -> None:
    source = make_source()
    with pytest.raises(ValidationError, match="updated_at"):
        Athlete(
            display_name="Example Athlete",
            verification_status=VerificationStatus.UNKNOWN,
            source_ids=[source.id],
            created_at=NOW,
            updated_at=NOW - timedelta(seconds=1),
        )

    with pytest.raises(ValidationError, match="Extra inputs"):
        Athlete(
            display_name="Example Athlete",
            verification_status=VerificationStatus.UNKNOWN,
            source_ids=[source.id],
            guessed_value="not allowed",
        )
