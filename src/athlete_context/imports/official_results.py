"""Mapping boundary for already-extracted official swimming results."""

from __future__ import annotations

from datetime import date
from typing import Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, AnyUrl, Field, field_validator, model_validator

from athlete_context.domain import (
    HistoricalResultStatus,
    PoolLength,
    RoundType,
    Source,
    SourceType,
    StandardStatus,
    Stroke,
    StructuredHistoricalResultInput,
    VerificationStatus,
)
from athlete_context.domain.models import (
    DomainModel,
    LanguageTag,
    NonEmptyText,
)
from athlete_context.services import (
    HistoricalResultIngestService,
    IngestOutcome,
)


class OfficialResultImport(DomainModel):
    """Already-extracted external official result plus explicit provenance."""

    source_id: UUID = Field(default_factory=uuid4)
    original_source: NonEmptyText
    original_language: LanguageTag | None = None
    captured_at: AwareDatetime
    source_type: SourceType
    source_reference: NonEmptyText | None = None
    source_url: AnyUrl | None = None

    athlete_id: UUID | None = None
    athlete_reference: NonEmptyText | None = None
    competition_id: UUID | None = None
    competition_reference: NonEmptyText | None = None
    event_id: UUID | None = None
    event_reference: NonEmptyText | None = None

    swim_date: date
    distance_m: int = Field(gt=0)
    stroke: Stroke
    pool_length: PoolLength
    official_time_raw: NonEmptyText
    round: RoundType = RoundType.UNKNOWN
    aqua_points: int | None = Field(default=None, ge=0)
    standard_status: StandardStatus = StandardStatus.UNKNOWN
    result_status: HistoricalResultStatus = HistoricalResultStatus.OFFICIAL
    verification_status: VerificationStatus

    @field_validator("source_type")
    @classmethod
    def require_known_source_type(cls, value: SourceType) -> SourceType:
        if value == SourceType.UNKNOWN:
            raise ValueError("source_type must be explicit")
        return value

    @model_validator(mode="after")
    def require_entity_identifiers_or_references(self) -> Self:
        missing = [
            name
            for name, entity_id, reference in (
                ("athlete", self.athlete_id, self.athlete_reference),
                ("competition", self.competition_id, self.competition_reference),
                ("event", self.event_id, self.event_reference),
            )
            if entity_id is None and reference is None
        ]
        if missing:
            raise ValueError(
                "official result import requires explicit entity IDs or references: "
                + ", ".join(missing)
            )
        return self


class OfficialResultImportMapping(DomainModel):
    """Existing Athlete Context records produced by the import boundary."""

    source: Source
    structured_result: StructuredHistoricalResultInput


class OfficialResultImportService:
    """Adapt structured official-result imports to the existing ingest service."""

    def map_import(
        self,
        result_import: OfficialResultImport,
    ) -> OfficialResultImportMapping:
        if not isinstance(result_import, OfficialResultImport):
            raise TypeError("result_import must be an OfficialResultImport")

        missing_ids = [
            name
            for name, value in (
                ("athlete_id", result_import.athlete_id),
                ("competition_id", result_import.competition_id),
                ("event_id", result_import.event_id),
            )
            if value is None
        ]
        if missing_ids:
            raise ValueError(
                "official result import requires explicit IDs before Layer 2 mapping: "
                + ", ".join(missing_ids)
            )

        source = Source(
            id=result_import.source_id,
            original_source=result_import.original_source,
            source_type=result_import.source_type,
            captured_at=result_import.captured_at,
            original_language=result_import.original_language,
            source_reference=result_import.source_reference,
            source_url=result_import.source_url,
            verification_status=result_import.verification_status,
            created_at=result_import.captured_at,
            updated_at=result_import.captured_at,
        )
        structured_result = StructuredHistoricalResultInput(
            athlete_id=result_import.athlete_id,
            competition_id=result_import.competition_id,
            event_id=result_import.event_id,
            swim_date=result_import.swim_date,
            round=result_import.round,
            distance_m=result_import.distance_m,
            stroke=result_import.stroke,
            pool_length=result_import.pool_length,
            official_time_raw=result_import.official_time_raw,
            aqua_points=result_import.aqua_points,
            standard_status=result_import.standard_status,
            result_status=result_import.result_status,
            verification_status=result_import.verification_status,
            source_id=result_import.source_id,
        )
        return OfficialResultImportMapping(
            source=source,
            structured_result=structured_result,
        )

    def import_result(
        self,
        result_import: OfficialResultImport,
        ingest_service: HistoricalResultIngestService,
    ) -> IngestOutcome:
        if not isinstance(ingest_service, HistoricalResultIngestService):
            raise TypeError("ingest_service must be a HistoricalResultIngestService")
        mapping = self.map_import(result_import)
        return ingest_service.ingest(
            mapping.structured_result,
            source=mapping.source,
        )
