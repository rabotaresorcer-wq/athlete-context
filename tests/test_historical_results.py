"""Deterministic coverage for Layer 2 historical result ingestion."""

from datetime import date, datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from athlete_context.domain import (
    HistoricalResultStatus,
    PoolLength,
    RoundType,
    Source,
    SourcePriority,
    SourceType,
    StandardStatus,
    Stroke,
    StructuredHistoricalResultInput,
    StructuredSplitInput,
    VerificationStatus,
    format_swim_time,
    parse_swim_time,
    source_priority,
)
from athlete_context.services import (
    HistoricalResultIngestService,
    InMemoryHistoricalResultRepository,
    IngestOutcomeStatus,
)

NOW = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
ATHLETE_ID = UUID("10000000-0000-0000-0000-000000000001")
COMPETITION_ID = UUID("20000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("30000000-0000-0000-0000-000000000001")


class DeterministicIdFactory:
    def __init__(self) -> None:
        self._next = 1

    def __call__(self) -> UUID:
        value = UUID(f"90000000-0000-0000-0000-{self._next:012d}")
        self._next += 1
        return value


def make_source(
    number: int,
    source_type: SourceType,
    verification_status: VerificationStatus,
) -> Source:
    source_id = UUID(f"40000000-0000-0000-0000-{number:012d}")
    return Source(
        id=source_id,
        original_source=f"Synthetic source {number}",
        source_type=source_type,
        captured_at=NOW,
        original_language="en",
        source_reference=f"synthetic-{number}",
        source_url=f"https://example.test/source/{number}",
        verification_status=verification_status,
        created_at=NOW,
        updated_at=NOW,
    )


def make_input(
    source_id: UUID,
    **updates: object,
) -> StructuredHistoricalResultInput:
    data: dict[str, object] = {
        "athlete_id": ATHLETE_ID,
        "competition_id": COMPETITION_ID,
        "event_id": EVENT_ID,
        "swim_date": date(2026, 1, 31),
        "round": RoundType.HEAT,
        "heat_number": 1,
        "lane": 4,
        "distance_m": 100,
        "stroke": Stroke.FREESTYLE,
        "pool_length": PoolLength.SCM_25M,
        "official_time_raw": "1:02.00",
        "splits": [],
        "aqua_points": None,
        "standard_status": StandardStatus.UNKNOWN,
        "result_status": HistoricalResultStatus.OFFICIAL,
        "verification_status": VerificationStatus.UNVERIFIED,
        "source_id": source_id,
        "notes": None,
    }
    data.update(updates)
    return StructuredHistoricalResultInput.model_validate(data)


def make_service() -> tuple[
    HistoricalResultIngestService, InMemoryHistoricalResultRepository
]:
    repository = InMemoryHistoricalResultRepository()
    service = HistoricalResultIngestService(
        repository,
        clock=lambda: NOW,
        id_factory=DeterministicIdFactory(),
    )
    return service, repository


def test_valid_short_course_result() -> None:
    source = make_source(
        1, SourceType.MANUAL_ENTRY, VerificationStatus.UNVERIFIED
    )
    service, _ = make_service()

    outcome = service.ingest(make_input(source.id), source=source)

    assert outcome.status == IngestOutcomeStatus.CREATED
    assert outcome.record is not None
    assert outcome.record.pool_length == PoolLength.SCM_25M
    assert outcome.record.official_time_centiseconds == 6200


def test_valid_long_course_result() -> None:
    source = make_source(
        2, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, _ = make_service()

    outcome = service.ingest(
        make_input(
            source.id,
            pool_length=PoolLength.LCM_50M,
            verification_status=VerificationStatus.VERIFIED,
        ),
        source=source,
    )

    assert outcome.status == IngestOutcomeStatus.CREATED
    assert outcome.record is not None
    assert outcome.record.pool_length == PoolLength.LCM_50M


@pytest.mark.parametrize(
    ("source_type", "expected"),
    [
        (
            SourceType.OFFICIAL_FEDERATION_RESULT,
            SourcePriority.OFFICIAL_FEDERATION_FINAL,
        ),
        (
            SourceType.OFFICIAL_COMPETITION_SYSTEM,
            SourcePriority.OFFICIAL_COMPETITION_SYSTEM,
        ),
        (
            SourceType.OFFICIAL_COMPETITION_DOCUMENT,
            SourcePriority.OFFICIAL_COMPETITION_DOCUMENT,
        ),
        (SourceType.CLUB_DOCUMENT, SourcePriority.CLUB_DOCUMENT),
        (
            SourceType.PROFESSIONAL_MESSAGE,
            SourcePriority.PROFESSIONAL_OR_COACH_MESSAGE,
        ),
        (SourceType.MANUAL_ENTRY, SourcePriority.SCREENSHOT_OR_MANUAL_ENTRY),
        (SourceType.OTHER_UNVERIFIED, SourcePriority.OTHER_UNVERIFIED),
    ],
)
def test_explicit_source_priority_order(
    source_type: SourceType, expected: SourcePriority
) -> None:
    source = make_source(26 + int(expected), source_type, VerificationStatus.VERIFIED)

    assert source_priority(source) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("34.19", 3419), ("1:17.07", 7707), ("2:47.85", 16785)],
)
def test_parse_swim_time(raw: str, expected: int) -> None:
    assert parse_swim_time(raw) == expected
    assert format_swim_time(expected) == raw


@pytest.mark.parametrize(
    "raw",
    ["34", "34.1", "34.190", "1:7.07", "1:77.07", "0:34.19", " 34.19"],
)
def test_invalid_time_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid or ambiguous"):
        parse_swim_time(raw)


@pytest.mark.parametrize(
    "status",
    [
        HistoricalResultStatus.DNS,
        HistoricalResultStatus.DNF,
        HistoricalResultStatus.DISQUALIFIED,
    ],
)
def test_non_finishing_status_accepts_missing_time(
    status: HistoricalResultStatus,
) -> None:
    source = make_source(
        3, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, _ = make_service()

    outcome = service.ingest(
        make_input(
            source.id,
            official_time_raw=None,
            result_status=status,
            verification_status=VerificationStatus.VERIFIED,
        ),
        source=source,
    )

    assert outcome.status == IngestOutcomeStatus.CREATED
    assert outcome.record is not None
    assert outcome.record.official_time_raw is None
    assert outcome.record.official_time_centiseconds is None


def test_structured_splits_are_normalized_and_preserved() -> None:
    source = make_source(
        4, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, _ = make_service()
    splits = [
        StructuredSplitInput(
            distance_m=50, split_time_raw="30.00", cumulative=True
        ),
        StructuredSplitInput(
            distance_m=100, split_time_raw="1:02.00", cumulative=True
        ),
    ]

    outcome = service.ingest(
        make_input(
            source.id,
            splits=splits,
            verification_status=VerificationStatus.VERIFIED,
        ),
        source=source,
    )

    assert outcome.record is not None
    assert [split.split_time_raw for split in outcome.record.splits] == [
        "30.00",
        "1:02.00",
    ]
    assert [split.split_time_centiseconds for split in outcome.record.splits] == [
        3000,
        6200,
    ]


@pytest.mark.parametrize(
    "splits",
    [
        [StructuredSplitInput(distance_m=150, split_time_raw="1:30.00", cumulative=True)],
        [
            StructuredSplitInput(
                distance_m=50, split_time_raw="30.00", cumulative=True
            ),
            StructuredSplitInput(
                distance_m=50, split_time_raw="31.00", cumulative=True
            ),
        ],
        [
            StructuredSplitInput(
                distance_m=50, split_time_raw="35.00", cumulative=True
            ),
            StructuredSplitInput(
                distance_m=100, split_time_raw="34.00", cumulative=True
            ),
        ],
    ],
)
def test_invalid_split_distance_or_chronology_is_rejected(
    splits: list[StructuredSplitInput],
) -> None:
    source = make_source(
        5, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, _ = make_service()

    outcome = service.ingest(make_input(source.id, splits=splits), source=source)

    assert outcome.status == IngestOutcomeStatus.REJECTED
    assert outcome.record is None


def test_exact_duplicate_is_idempotent() -> None:
    source = make_source(
        6, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, repository = make_service()
    structured = make_input(
        source.id, verification_status=VerificationStatus.VERIFIED
    )

    first = service.ingest(structured, source=source)
    second = service.ingest(structured, source=source)

    assert first.status == IngestOutcomeStatus.CREATED
    assert second.status == IngestOutcomeStatus.DUPLICATE
    assert len(repository.all()) == 1
    assert first.record is not None
    assert len(repository.claims_for(first.record.id)) == 1


def test_same_swim_from_second_source_is_linked_without_duplicate() -> None:
    first_source = make_source(
        7, SourceType.MANUAL_ENTRY, VerificationStatus.UNVERIFIED
    )
    second_source = make_source(
        8, SourceType.CLUB_DOCUMENT, VerificationStatus.UNVERIFIED
    )
    service, repository = make_service()

    first = service.ingest(make_input(first_source.id), source=first_source)
    second = service.ingest(make_input(second_source.id), source=second_source)

    assert second.status == IngestOutcomeStatus.DUPLICATE
    assert second.record is not None
    assert len(repository.all()) == 1
    assert second.record.source_ids == [first_source.id, second_source.id]
    assert first.record is not None
    assert len(repository.claims_for(first.record.id)) == 2


def test_higher_priority_verified_source_replaces_lower_unverified_claim() -> None:
    manual = make_source(
        9, SourceType.MANUAL_ENTRY, VerificationStatus.UNVERIFIED
    )
    federation = make_source(
        10, SourceType.OFFICIAL_FEDERATION_RESULT, VerificationStatus.VERIFIED
    )
    service, repository = make_service()

    first = service.ingest(make_input(manual.id, official_time_raw="1:02.00"), source=manual)
    updated = service.ingest(
        make_input(
            federation.id,
            official_time_raw="1:01.80",
            verification_status=VerificationStatus.VERIFIED,
        ),
        source=federation,
    )

    assert updated.status == IngestOutcomeStatus.UPDATED_FROM_HIGHER_PRIORITY_SOURCE
    assert updated.record is not None
    assert first.record is not None
    assert updated.record.id == first.record.id
    assert updated.record.official_time_centiseconds == 6180
    assert updated.record.source_id == federation.id
    assert len(repository.claims_for(updated.record.id)) == 2


def test_lower_priority_source_does_not_overwrite_verified_official_result() -> None:
    federation = make_source(
        11, SourceType.OFFICIAL_FEDERATION_RESULT, VerificationStatus.VERIFIED
    )
    manual = make_source(
        12, SourceType.MANUAL_ENTRY, VerificationStatus.UNVERIFIED
    )
    service, repository = make_service()

    official = service.ingest(
        make_input(
            federation.id,
            official_time_raw="1:01.80",
            verification_status=VerificationStatus.VERIFIED,
        ),
        source=federation,
    )
    rejected = service.ingest(
        make_input(manual.id, official_time_raw="1:02.50"), source=manual
    )

    assert rejected.status == IngestOutcomeStatus.REJECTED
    assert rejected.record is not None
    assert rejected.record.official_time_centiseconds == 6180
    assert rejected.record.verification_status == VerificationStatus.VERIFIED
    assert official.record is not None
    assert len(repository.claims_for(official.record.id)) == 2


def test_conflicting_official_claims_produce_traceable_conflict() -> None:
    first_source = make_source(
        13, SourceType.OFFICIAL_FEDERATION_RESULT, VerificationStatus.VERIFIED
    )
    second_source = make_source(
        14, SourceType.OFFICIAL_FEDERATION_RESULT, VerificationStatus.VERIFIED
    )
    service, repository = make_service()

    first = service.ingest(
        make_input(
            first_source.id,
            official_time_raw="1:01.80",
            verification_status=VerificationStatus.VERIFIED,
        ),
        source=first_source,
    )
    conflict = service.ingest(
        make_input(
            second_source.id,
            official_time_raw="1:01.70",
            verification_status=VerificationStatus.VERIFIED,
        ),
        source=second_source,
    )

    assert conflict.status == IngestOutcomeStatus.CONFLICT
    assert conflict.record is not None
    assert conflict.record.verification_status == VerificationStatus.CONFLICT
    assert conflict.record.official_time_centiseconds == 6180
    assert first.record is not None
    claims = repository.claims_for(first.record.id)
    assert [claim.official_time_centiseconds for claim in claims] == [6180, 6170]


def test_different_rounds_are_not_deduplicated() -> None:
    source = make_source(
        15, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, repository = make_service()

    heat = service.ingest(make_input(source.id, round=RoundType.HEAT), source=source)
    final = service.ingest(make_input(source.id, round=RoundType.FINAL), source=source)

    assert heat.status == IngestOutcomeStatus.CREATED
    assert final.status == IngestOutcomeStatus.CREATED
    assert len(repository.all()) == 2


def test_different_known_heats_are_not_deduplicated() -> None:
    source = make_source(
        16, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, repository = make_service()

    first = service.ingest(make_input(source.id, heat_number=1), source=source)
    second = service.ingest(make_input(source.id, heat_number=2), source=source)

    assert first.status == IngestOutcomeStatus.CREATED
    assert second.status == IngestOutcomeStatus.CREATED
    assert len(repository.all()) == 2


def test_short_and_long_course_results_remain_distinct() -> None:
    source = make_source(
        17, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, repository = make_service()

    short_course = service.ingest(
        make_input(source.id, pool_length=PoolLength.SCM_25M), source=source
    )
    long_course = service.ingest(
        make_input(source.id, pool_length=PoolLength.LCM_50M), source=source
    )

    assert short_course.status == IngestOutcomeStatus.CREATED
    assert long_course.status == IngestOutcomeStatus.CREATED
    assert len(repository.all()) == 2


def test_aqua_points_are_preserved_when_supplied() -> None:
    source = make_source(
        18, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, _ = make_service()

    outcome = service.ingest(make_input(source.id, aqua_points=712), source=source)

    assert outcome.record is not None
    assert outcome.record.aqua_points == 712


def test_missing_aqua_points_are_accepted_without_calculation() -> None:
    source = make_source(
        19, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, _ = make_service()

    outcome = service.ingest(make_input(source.id, aqua_points=None), source=source)

    assert outcome.record is not None
    assert outcome.record.aqua_points is None


def test_standard_status_is_preserved_without_calculation() -> None:
    source = make_source(
        20, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, _ = make_service()

    outcome = service.ingest(
        make_input(source.id, standard_status=StandardStatus.NOT_PASSED),
        source=source,
    )

    assert outcome.record is not None
    assert outcome.record.standard_status == StandardStatus.NOT_PASSED


def test_provenance_remains_traceable_to_all_linked_sources() -> None:
    first_source = make_source(
        21, SourceType.MANUAL_ENTRY, VerificationStatus.UNVERIFIED
    )
    second_source = make_source(
        22, SourceType.CLUB_DOCUMENT, VerificationStatus.UNVERIFIED
    )
    service, repository = make_service()

    service.ingest(make_input(first_source.id), source=first_source)
    linked = service.ingest(make_input(second_source.id), source=second_source)

    assert linked.record is not None
    sources = repository.sources_for(linked.record.id)
    assert [source.id for source in sources] == [first_source.id, second_source.id]
    assert all(source.original_source.startswith("Synthetic source") for source in sources)


def test_source_id_mismatch_is_rejected() -> None:
    source = make_source(
        23, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    other_source = make_source(
        24, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )
    service, repository = make_service()

    outcome = service.ingest(make_input(other_source.id), source=source)

    assert outcome.status == IngestOutcomeStatus.REJECTED
    assert outcome.record is None
    assert repository.all() == ()


def test_structured_input_rejects_timed_status_without_time() -> None:
    source = make_source(
        25, SourceType.OFFICIAL_COMPETITION_SYSTEM, VerificationStatus.VERIFIED
    )

    with pytest.raises(ValidationError, match="require an official time"):
        make_input(
            source.id,
            official_time_raw=None,
            result_status=HistoricalResultStatus.OFFICIAL,
        )
