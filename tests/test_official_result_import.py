"""Focused coverage for structured official-result import mapping."""

from datetime import date, datetime, timezone
from subprocess import run
from uuid import UUID

import pytest

from athlete_context.domain import (
    HistoricalResultStatus,
    PoolLength,
    RoundType,
    SourceType,
    StandardStatus,
    Stroke,
    VerificationStatus,
)
from athlete_context.imports import OfficialResultImport, OfficialResultImportService
from athlete_context.services import (
    HistoricalResultIngestService,
    InMemoryHistoricalResultRepository,
    IngestOutcomeStatus,
)

NOW = datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)
ATHLETE_ID = UUID("b1000000-0000-0000-0000-000000000001")
COMPETITION_ID = UUID("b2000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("b3000000-0000-0000-0000-000000000001")


class DeterministicIdFactory:
    def __init__(self) -> None:
        self._next = 1

    def __call__(self) -> UUID:
        value = UUID(f"b9000000-0000-0000-0000-{self._next:012d}")
        self._next += 1
        return value


def make_import(
    number: int,
    *,
    source_type: SourceType = SourceType.OFFICIAL_FEDERATION_RESULT,
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
    pool_length: PoolLength = PoolLength.LCM_50M,
    raw_time: str = "59.50",
) -> OfficialResultImport:
    return OfficialResultImport(
        source_id=UUID(f"b4000000-0000-0000-0000-{number:012d}"),
        original_source=f"Synthetic official result source {number}",
        original_language="tr",
        captured_at=NOW,
        source_type=source_type,
        source_reference=f"synthetic-official-result:{number}",
        source_url=f"https://example.test/synthetic-results/{number}",
        athlete_id=ATHLETE_ID,
        athlete_reference="synthetic-athlete:northstar",
        competition_id=COMPETITION_ID,
        competition_reference="synthetic-competition:horizon",
        event_id=EVENT_ID,
        event_reference="synthetic-event:100-free",
        swim_date=date(2026, 9, 1),
        distance_m=100,
        stroke=Stroke.FREESTYLE,
        pool_length=pool_length,
        official_time_raw=raw_time,
        round=RoundType.FINAL,
        aqua_points=612,
        standard_status=StandardStatus.UNKNOWN,
        result_status=HistoricalResultStatus.OFFICIAL,
        verification_status=verification_status,
    )


def make_ingest_service() -> tuple[
    HistoricalResultIngestService, InMemoryHistoricalResultRepository
]:
    repository = InMemoryHistoricalResultRepository()
    service = HistoricalResultIngestService(
        repository,
        clock=lambda: NOW,
        id_factory=DeterministicIdFactory(),
    )
    return service, repository


def test_structured_official_import_maps_to_existing_input() -> None:
    result_import = make_import(1)

    mapping = OfficialResultImportService().map_import(result_import)

    assert mapping.structured_result.athlete_id == ATHLETE_ID
    assert mapping.structured_result.competition_id == COMPETITION_ID
    assert mapping.structured_result.event_id == EVENT_ID
    assert mapping.structured_result.swim_date == date(2026, 9, 1)
    assert mapping.structured_result.distance_m == 100
    assert mapping.structured_result.stroke == Stroke.FREESTYLE
    assert mapping.structured_result.pool_length == PoolLength.LCM_50M
    assert mapping.structured_result.official_time_raw == "59.50"
    assert mapping.structured_result.round == RoundType.FINAL
    assert mapping.structured_result.aqua_points == 612


def test_verification_status_is_preserved_exactly() -> None:
    result_import = make_import(
        2,
        verification_status=VerificationStatus.UNVERIFIED,
    )

    mapping = OfficialResultImportService().map_import(result_import)

    assert mapping.source.verification_status == VerificationStatus.UNVERIFIED
    assert mapping.structured_result.verification_status == VerificationStatus.UNVERIFIED


def test_provenance_survives_mapping_and_ingestion() -> None:
    result_import = make_import(3)
    ingest_service, repository = make_ingest_service()

    outcome = OfficialResultImportService().import_result(
        result_import,
        ingest_service,
    )

    assert outcome.status == IngestOutcomeStatus.CREATED
    assert outcome.record is not None
    assert outcome.record.source_id == result_import.source_id
    source = repository.sources_for(outcome.record.id)[0]
    assert source.original_source == result_import.original_source
    assert source.source_reference == result_import.source_reference
    assert str(source.source_url) == str(result_import.source_url)
    assert source.original_language == result_import.original_language


def test_pool_length_is_preserved_and_keeps_scm_lcm_separate() -> None:
    ingest_service, repository = make_ingest_service()
    service = OfficialResultImportService()

    lcm = service.import_result(
        make_import(4, pool_length=PoolLength.LCM_50M, raw_time="59.50"),
        ingest_service,
    )
    scm = service.import_result(
        make_import(5, pool_length=PoolLength.SCM_25M, raw_time="57.80"),
        ingest_service,
    )

    assert lcm.status == IngestOutcomeStatus.CREATED
    assert scm.status == IngestOutcomeStatus.CREATED
    assert lcm.record is not None
    assert scm.record is not None
    assert lcm.record.pool_length == PoolLength.LCM_50M
    assert scm.record.pool_length == PoolLength.SCM_25M
    assert len(repository.all()) == 2


def test_duplicate_import_uses_existing_ingestion_determinism() -> None:
    result_import = make_import(6)
    ingest_service, repository = make_ingest_service()
    service = OfficialResultImportService()

    first = service.import_result(result_import, ingest_service)
    second = service.import_result(result_import, ingest_service)

    assert first.status == IngestOutcomeStatus.CREATED
    assert second.status == IngestOutcomeStatus.DUPLICATE
    assert first.record is not None
    assert second.record is not None
    assert second.record.id == first.record.id
    assert len(repository.all()) == 1


def test_reference_only_import_is_not_resolved_by_adapter() -> None:
    reference_only = make_import(9).model_copy(
        update={
            "athlete_id": None,
            "competition_id": None,
            "event_id": None,
        }
    )

    with pytest.raises(ValueError, match="requires explicit IDs"):
        OfficialResultImportService().map_import(reference_only)


def test_lower_priority_conflict_does_not_overwrite_verified_official_result() -> None:
    ingest_service, repository = make_ingest_service()
    service = OfficialResultImportService()

    official = service.import_result(make_import(7, raw_time="59.50"), ingest_service)
    lower_priority = service.import_result(
        make_import(
            8,
            source_type=SourceType.MANUAL_ENTRY,
            verification_status=VerificationStatus.UNVERIFIED,
            raw_time="1:00.20",
        ),
        ingest_service,
    )

    assert official.record is not None
    assert lower_priority.status == IngestOutcomeStatus.REJECTED
    assert lower_priority.record is not None
    assert lower_priority.record.id == official.record.id
    assert lower_priority.record.official_time_raw == "59.50"
    assert lower_priority.record.verification_status == VerificationStatus.VERIFIED
    assert len(repository.claims_for(official.record.id)) == 2


def test_private_data_path_is_ignored_for_real_import_material() -> None:
    ignored = run(
        ["git", "check-ignore", "data/private/example.json"],
        check=False,
        capture_output=True,
        text=True,
    )
    tracked = run(
        ["git", "ls-files", "data/private"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert ignored.returncode == 0
    assert tracked.stdout == ""
