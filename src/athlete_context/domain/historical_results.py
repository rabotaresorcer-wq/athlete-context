"""Historical swim result models and deterministic normalization helpers."""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import IntEnum, StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from athlete_context.domain.models import (
    DomainModel,
    Entity,
    NonEmptyText,
    Source,
    SourceType,
    VerificationStatus,
)

_SHORT_TIME_PATTERN = re.compile(r"(?P<seconds>[0-5]?\d)\.(?P<centiseconds>\d{2})")
_LONG_TIME_PATTERN = re.compile(
    r"(?P<minutes>[1-9]\d*):(?P<seconds>[0-5]\d)\.(?P<centiseconds>\d{2})"
)


class PoolLength(StrEnum):
    SCM_25M = "SCM_25M"
    LCM_50M = "LCM_50M"
    UNKNOWN = "UNKNOWN"


class Stroke(StrEnum):
    FREESTYLE = "FREESTYLE"
    BACKSTROKE = "BACKSTROKE"
    BREASTSTROKE = "BREASTSTROKE"
    BUTTERFLY = "BUTTERFLY"
    MEDLEY = "MEDLEY"
    UNKNOWN = "UNKNOWN"


class RoundType(StrEnum):
    HEAT = "HEAT"
    FINAL = "FINAL"
    TIME_TRIAL = "TIME_TRIAL"
    UNKNOWN = "UNKNOWN"


class ResultStatus(StrEnum):
    OFFICIAL = "OFFICIAL"
    PROVISIONAL = "PROVISIONAL"
    REPORTED = "REPORTED"
    DISQUALIFIED = "DISQUALIFIED"
    DNS = "DNS"
    DNF = "DNF"
    UNKNOWN = "UNKNOWN"


class StandardStatus(StrEnum):
    PASSED = "PASSED"
    NOT_PASSED = "NOT_PASSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class SourcePriority(IntEnum):
    OFFICIAL_FEDERATION_FINAL = 1
    OFFICIAL_COMPETITION_SYSTEM = 2
    OFFICIAL_COMPETITION_DOCUMENT = 3
    CLUB_DOCUMENT = 4
    PROFESSIONAL_OR_COACH_MESSAGE = 5
    SCREENSHOT_OR_MANUAL_ENTRY = 6
    OTHER_UNVERIFIED = 7


_SOURCE_PRIORITIES: dict[SourceType, SourcePriority] = {
    SourceType.OFFICIAL_FEDERATION_RESULT: SourcePriority.OFFICIAL_FEDERATION_FINAL,
    SourceType.FEDERATION_PUBLICATION: SourcePriority.OFFICIAL_COMPETITION_DOCUMENT,
    SourceType.OFFICIAL_COMPETITION_SYSTEM: SourcePriority.OFFICIAL_COMPETITION_SYSTEM,
    SourceType.OFFICIAL_RESULT: SourcePriority.OFFICIAL_COMPETITION_SYSTEM,
    SourceType.COMPETITION_ORGANIZER: SourcePriority.OFFICIAL_COMPETITION_SYSTEM,
    SourceType.OFFICIAL_COMPETITION_DOCUMENT: SourcePriority.OFFICIAL_COMPETITION_DOCUMENT,
    SourceType.DOCUMENT: SourcePriority.OTHER_UNVERIFIED,
    SourceType.CLUB_DOCUMENT: SourcePriority.CLUB_DOCUMENT,
    SourceType.PROFESSIONAL_MESSAGE: SourcePriority.PROFESSIONAL_OR_COACH_MESSAGE,
    SourceType.PROFESSIONAL_FEEDBACK: SourcePriority.PROFESSIONAL_OR_COACH_MESSAGE,
    SourceType.MESSAGE: SourcePriority.OTHER_UNVERIFIED,
    SourceType.SCREENSHOT: SourcePriority.SCREENSHOT_OR_MANUAL_ENTRY,
    SourceType.MANUAL_ENTRY: SourcePriority.SCREENSHOT_OR_MANUAL_ENTRY,
    SourceType.ATHLETE_PROVIDED: SourcePriority.SCREENSHOT_OR_MANUAL_ENTRY,
    SourceType.MEDIA: SourcePriority.SCREENSHOT_OR_MANUAL_ENTRY,
    SourceType.OTHER_UNVERIFIED: SourcePriority.OTHER_UNVERIFIED,
    SourceType.OTHER: SourcePriority.OTHER_UNVERIFIED,
    SourceType.UNKNOWN: SourcePriority.OTHER_UNVERIFIED,
}


def parse_swim_time(value: str) -> int:
    """Parse an unambiguous source time into integer centiseconds."""

    if not isinstance(value, str):
        raise TypeError("swim time must be a string")

    match = _SHORT_TIME_PATTERN.fullmatch(value)
    if match:
        total = int(match["seconds"]) * 100 + int(match["centiseconds"])
    else:
        match = _LONG_TIME_PATTERN.fullmatch(value)
        if not match:
            raise ValueError("invalid or ambiguous swim time format")
        total = (
            int(match["minutes"]) * 60 * 100
            + int(match["seconds"]) * 100
            + int(match["centiseconds"])
        )

    if total <= 0:
        raise ValueError("swim time must be greater than zero")
    return total


def format_swim_time(centiseconds: int) -> str:
    """Format positive integer centiseconds using canonical swim notation."""

    if isinstance(centiseconds, bool) or not isinstance(centiseconds, int):
        raise TypeError("centiseconds must be an integer")
    if centiseconds <= 0:
        raise ValueError("centiseconds must be greater than zero")

    total_seconds, hundredths = divmod(centiseconds, 100)
    minutes, seconds = divmod(total_seconds, 60)
    if minutes:
        return f"{minutes}:{seconds:02d}.{hundredths:02d}"
    return f"{seconds}.{hundredths:02d}"


def source_priority(source: Source) -> SourcePriority:
    """Return the explicit provenance priority for a source category."""

    return _SOURCE_PRIORITIES[source.source_type]


class StructuredSplitInput(DomainModel):
    """Already-structured split input before time normalization."""

    distance_m: int = Field(gt=0)
    split_time_raw: str = Field(min_length=1)
    cumulative: bool

    @field_validator("split_time_raw")
    @classmethod
    def validate_raw_time(cls, value: str) -> str:
        parse_swim_time(value)
        return value


class Split(DomainModel):
    """A source-preserving normalized split."""

    distance_m: int = Field(gt=0)
    split_time_raw: str = Field(min_length=1)
    split_time_centiseconds: int = Field(gt=0)
    cumulative: bool

    @model_validator(mode="after")
    def validate_normalized_time(self) -> Self:
        if parse_swim_time(self.split_time_raw) != self.split_time_centiseconds:
            raise ValueError(
                "split_time_centiseconds must match the preserved split_time_raw"
            )
        return self


class StructuredHistoricalResultInput(DomainModel):
    """Validated structured input accepted by the Layer 2 ingest service."""

    athlete_id: UUID
    competition_id: UUID
    event_id: UUID
    swim_date: date
    round: RoundType
    heat_number: int | None = Field(default=None, ge=1)
    lane: int | None = Field(default=None, ge=1)
    distance_m: int = Field(gt=0)
    stroke: Stroke
    pool_length: PoolLength
    official_time_raw: str | None = None
    splits: list[StructuredSplitInput] = Field(default_factory=list)
    aqua_points: int | None = Field(default=None, ge=0)
    standard_status: StandardStatus
    result_status: ResultStatus
    verification_status: VerificationStatus
    source_id: UUID
    notes: NonEmptyText | None = None

    @model_validator(mode="after")
    def validate_time_presence(self) -> Self:
        if self.official_time_raw is not None:
            parse_swim_time(self.official_time_raw)
        elif self.result_status in {
            ResultStatus.OFFICIAL,
            ResultStatus.PROVISIONAL,
            ResultStatus.REPORTED,
        }:
            raise ValueError(f"{self.result_status} results require an official time")
        return self


class HistoricalResult(Entity):
    """One source-traceable athlete swim in a competition event."""

    athlete_id: UUID
    competition_id: UUID
    event_id: UUID
    swim_date: date
    round: RoundType
    heat_number: int | None = Field(default=None, ge=1)
    lane: int | None = Field(default=None, ge=1)
    distance_m: int = Field(gt=0)
    stroke: Stroke
    pool_length: PoolLength
    official_time_raw: str | None = None
    official_time_centiseconds: int | None = Field(default=None, gt=0)
    splits: list[Split] = Field(default_factory=list)
    aqua_points: int | None = Field(default=None, ge=0)
    standard_status: StandardStatus
    result_status: ResultStatus
    verification_status: VerificationStatus
    source_id: UUID
    source_ids: list[UUID] = Field(min_length=1)
    notes: NonEmptyText | None = None

    @field_validator("source_ids")
    @classmethod
    def validate_unique_sources(cls, source_ids: list[UUID]) -> list[UUID]:
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_ids must be unique")
        return source_ids

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.source_id not in self.source_ids:
            raise ValueError("source_id must be present in source_ids")
        if (self.official_time_raw is None) != (
            self.official_time_centiseconds is None
        ):
            raise ValueError(
                "official_time_raw and official_time_centiseconds must be provided together"
            )
        if self.official_time_raw is not None:
            parsed = parse_swim_time(self.official_time_raw)
            if parsed != self.official_time_centiseconds:
                raise ValueError(
                    "official_time_centiseconds must match official_time_raw"
                )
        elif self.result_status in {
            ResultStatus.OFFICIAL,
            ResultStatus.PROVISIONAL,
            ResultStatus.REPORTED,
        }:
            raise ValueError(f"{self.result_status} results require an official time")

        previous_distance = 0
        previous_cumulative_time: int | None = None
        for split in self.splits:
            if split.distance_m <= previous_distance:
                raise ValueError("split distances must be strictly increasing")
            if split.distance_m > self.distance_m:
                raise ValueError("split distance must not exceed event distance")
            previous_distance = split.distance_m

            if split.cumulative:
                if (
                    previous_cumulative_time is not None
                    and split.split_time_centiseconds <= previous_cumulative_time
                ):
                    raise ValueError(
                        "cumulative split times must be chronologically increasing"
                    )
                previous_cumulative_time = split.split_time_centiseconds
                if (
                    self.official_time_centiseconds is not None
                    and split.split_time_centiseconds
                    > self.official_time_centiseconds
                ):
                    raise ValueError("cumulative split cannot exceed official time")
                if (
                    split.distance_m == self.distance_m
                    and self.official_time_centiseconds is not None
                    and split.split_time_centiseconds
                    != self.official_time_centiseconds
                ):
                    raise ValueError(
                        "final cumulative split must match the official time"
                    )
        return self

    def identity_key(self) -> tuple[UUID, UUID, UUID, date, RoundType, PoolLength]:
        """Return the stable primary identity excluding optional heat metadata."""

        return (
            self.athlete_id,
            self.competition_id,
            self.event_id,
            self.swim_date,
            self.round,
            self.pool_length,
        )

    def claim_fingerprint(self) -> tuple[object, ...]:
        """Return normalized claim values used for duplicate/conflict checks."""

        return (
            self.distance_m,
            self.stroke,
            self.pool_length,
            self.official_time_centiseconds,
            tuple(
                (
                    split.distance_m,
                    split.split_time_centiseconds,
                    split.cumulative,
                )
                for split in self.splits
            ),
            self.aqua_points,
            self.standard_status,
            self.result_status,
        )


def normalize_historical_result(
    structured: StructuredHistoricalResultInput,
    *,
    record_id: UUID,
    timestamp: datetime,
) -> HistoricalResult:
    """Normalize validated structured input without parsing any source document."""

    return HistoricalResult(
        id=record_id,
        athlete_id=structured.athlete_id,
        competition_id=structured.competition_id,
        event_id=structured.event_id,
        swim_date=structured.swim_date,
        round=structured.round,
        heat_number=structured.heat_number,
        lane=structured.lane,
        distance_m=structured.distance_m,
        stroke=structured.stroke,
        pool_length=structured.pool_length,
        official_time_raw=structured.official_time_raw,
        official_time_centiseconds=(
            parse_swim_time(structured.official_time_raw)
            if structured.official_time_raw is not None
            else None
        ),
        splits=[
            Split(
                distance_m=split.distance_m,
                split_time_raw=split.split_time_raw,
                split_time_centiseconds=parse_swim_time(split.split_time_raw),
                cumulative=split.cumulative,
            )
            for split in structured.splits
        ],
        aqua_points=structured.aqua_points,
        standard_status=structured.standard_status,
        result_status=structured.result_status,
        verification_status=structured.verification_status,
        source_id=structured.source_id,
        source_ids=[structured.source_id],
        notes=structured.notes,
        created_at=timestamp,
        updated_at=timestamp,
    )
