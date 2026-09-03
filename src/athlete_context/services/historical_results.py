"""Persistence-agnostic ingestion for already-structured historical results."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError

from athlete_context.domain.historical_results import (
    HistoricalResult,
    SourcePriority,
    StructuredHistoricalResultInput,
    normalize_historical_result,
    source_priority,
)
from athlete_context.domain.models import (
    DomainModel,
    Source,
    VerificationStatus,
    utc_now,
)


class IngestOutcomeStatus(StrEnum):
    CREATED = "CREATED"
    DUPLICATE = "DUPLICATE"
    UPDATED_FROM_HIGHER_PRIORITY_SOURCE = "UPDATED_FROM_HIGHER_PRIORITY_SOURCE"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"


class IngestOutcome(DomainModel):
    """Explicit result of one structured ingest attempt."""

    status: IngestOutcomeStatus
    record: HistoricalResult | None
    claim: HistoricalResult | None = None
    message: str


class HistoricalResultRepository(Protocol):
    """Storage contract required by the domain ingest service."""

    def register_source(self, source: Source) -> None: ...

    def get_source(self, source_id: UUID) -> Source: ...

    def find_identity_matches(
        self, incoming: HistoricalResult
    ) -> tuple[HistoricalResult, ...]: ...

    def add(self, record: HistoricalResult) -> None: ...

    def update(self, record: HistoricalResult) -> None: ...

    def add_claim(self, record_id: UUID, claim: HistoricalResult) -> None: ...

    def claims_for(self, record_id: UUID) -> tuple[HistoricalResult, ...]: ...


class InMemoryHistoricalResultRepository:
    """Deterministic in-memory repository/test double; not production persistence."""

    def __init__(self) -> None:
        self._records: dict[UUID, HistoricalResult] = {}
        self._claims: dict[UUID, list[HistoricalResult]] = {}
        self._sources: dict[UUID, Source] = {}

    def register_source(self, source: Source) -> None:
        existing = self._sources.get(source.id)
        if existing is not None and existing != source:
            raise ValueError("source id is already registered with different provenance")
        self._sources[source.id] = source

    def get_source(self, source_id: UUID) -> Source:
        return self._sources[source_id]

    def find_identity_matches(
        self, incoming: HistoricalResult
    ) -> tuple[HistoricalResult, ...]:
        matches = []
        for record in self._records.values():
            if record.identity_key() != incoming.identity_key():
                continue
            if (
                record.heat_number is not None
                and incoming.heat_number is not None
                and record.heat_number != incoming.heat_number
            ):
                continue
            matches.append(record)
        return tuple(matches)

    def add(self, record: HistoricalResult) -> None:
        if record.id in self._records:
            raise ValueError("historical result id already exists")
        self._records[record.id] = record
        self._claims[record.id] = [record]

    def update(self, record: HistoricalResult) -> None:
        if record.id not in self._records:
            raise KeyError(record.id)
        self._records[record.id] = record

    def add_claim(self, record_id: UUID, claim: HistoricalResult) -> None:
        claims = self._claims[record_id]
        if any(_exact_claim(existing, claim) for existing in claims):
            return
        claims.append(claim)

    def all(self) -> tuple[HistoricalResult, ...]:
        return tuple(self._records.values())

    def get(self, record_id: UUID) -> HistoricalResult:
        return self._records[record_id]

    def claims_for(self, record_id: UUID) -> tuple[HistoricalResult, ...]:
        return tuple(self._claims[record_id])

    def sources_for(self, record_id: UUID) -> tuple[Source, ...]:
        record = self.get(record_id)
        return tuple(self._sources[source_id] for source_id in record.source_ids)


def _exact_claim(left: HistoricalResult, right: HistoricalResult) -> bool:
    excluded = {"id", "created_at", "updated_at", "source_ids"}
    return left.model_dump(exclude=excluded) == right.model_dump(exclude=excluded)


def _merge_source_ids(existing: HistoricalResult, incoming: HistoricalResult) -> list[UUID]:
    return list(dict.fromkeys([*existing.source_ids, *incoming.source_ids]))


def _rebuild_record(
    source_record: HistoricalResult,
    *,
    record_id: UUID,
    created_at: datetime,
    updated_at: datetime,
    source_ids: list[UUID],
    verification_status: VerificationStatus | None = None,
) -> HistoricalResult:
    data = source_record.model_dump()
    data.update(
        id=record_id,
        created_at=created_at,
        updated_at=updated_at,
        source_ids=source_ids,
    )
    if verification_status is not None:
        data["verification_status"] = verification_status
    return HistoricalResult.model_validate(data)


class HistoricalResultIngestService:
    """Validate, normalize, deduplicate, prioritize, and retain source claims."""

    def __init__(
        self,
        repository: HistoricalResultRepository,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._id_factory = id_factory

    def ingest(
        self,
        payload: StructuredHistoricalResultInput | Mapping[str, Any],
        *,
        source: Source,
    ) -> IngestOutcome:
        try:
            structured = (
                payload
                if isinstance(payload, StructuredHistoricalResultInput)
                else StructuredHistoricalResultInput.model_validate(payload)
            )
        except (ValidationError, ValueError, TypeError) as error:
            return IngestOutcome(
                status=IngestOutcomeStatus.REJECTED,
                record=None,
                message=f"structured input rejected: {error}",
            )

        if structured.source_id != source.id:
            return IngestOutcome(
                status=IngestOutcomeStatus.REJECTED,
                record=None,
                message="structured source_id does not match supplied provenance",
            )

        try:
            self._repository.register_source(source)
            incoming = normalize_historical_result(
                structured,
                record_id=self._id_factory(),
                timestamp=self._clock(),
            )
        except (ValidationError, ValueError, TypeError) as error:
            return IngestOutcome(
                status=IngestOutcomeStatus.REJECTED,
                record=None,
                message=f"normalization rejected: {error}",
            )

        matches = self._repository.find_identity_matches(incoming)
        if not matches:
            self._repository.add(incoming)
            return IngestOutcome(
                status=IngestOutcomeStatus.CREATED,
                record=incoming,
                claim=incoming,
                message="new historical swim created",
            )
        if len(matches) > 1:
            return IngestOutcome(
                status=IngestOutcomeStatus.REJECTED,
                record=None,
                claim=incoming,
                message="optional heat is insufficient to select one existing swim",
            )

        existing = matches[0]
        existing_claims = self._repository.claims_for(existing.id)
        if any(_exact_claim(claim, incoming) for claim in existing_claims):
            return IngestOutcome(
                status=IngestOutcomeStatus.DUPLICATE,
                record=existing,
                claim=incoming,
                message="exact claim already ingested",
            )

        self._repository.add_claim(existing.id, incoming)
        merged_source_ids = _merge_source_ids(existing, incoming)
        timestamp = self._clock()

        if existing.claim_fingerprint() == incoming.claim_fingerprint():
            linked = _rebuild_record(
                existing,
                record_id=existing.id,
                created_at=existing.created_at,
                updated_at=timestamp,
                source_ids=merged_source_ids,
            )
            self._repository.update(linked)
            return IngestOutcome(
                status=IngestOutcomeStatus.DUPLICATE,
                record=linked,
                claim=incoming,
                message="same swim linked to an additional source",
            )

        existing_source = self._repository.get_source(existing.source_id)
        existing_priority = source_priority(existing_source)
        incoming_priority = source_priority(source)

        if (
            incoming_priority < existing_priority
            and source.verification_status == VerificationStatus.VERIFIED
            and existing.verification_status != VerificationStatus.VERIFIED
        ):
            updated = _rebuild_record(
                incoming,
                record_id=existing.id,
                created_at=existing.created_at,
                updated_at=timestamp,
                source_ids=merged_source_ids,
            )
            self._repository.update(updated)
            return IngestOutcome(
                status=IngestOutcomeStatus.UPDATED_FROM_HIGHER_PRIORITY_SOURCE,
                record=updated,
                claim=incoming,
                message="higher-priority verified claim became canonical",
            )

        if (
            existing.verification_status == VerificationStatus.VERIFIED
            and existing_priority < incoming_priority
        ):
            retained = _rebuild_record(
                existing,
                record_id=existing.id,
                created_at=existing.created_at,
                updated_at=timestamp,
                source_ids=merged_source_ids,
            )
            self._repository.update(retained)
            return IngestOutcome(
                status=IngestOutcomeStatus.REJECTED,
                record=retained,
                claim=incoming,
                message="lower-priority claim retained for traceability without overwrite",
            )

        conflicted = _rebuild_record(
            existing,
            record_id=existing.id,
            created_at=existing.created_at,
            updated_at=timestamp,
            source_ids=merged_source_ids,
            verification_status=VerificationStatus.CONFLICT,
        )
        self._repository.update(conflicted)
        return IngestOutcome(
            status=IngestOutcomeStatus.CONFLICT,
            record=conflicted,
            claim=incoming,
            message="incompatible claims retained and marked as conflict",
        )
