"""Validated, persistence-independent domain models for Athlete Context."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    AnyUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
LanguageTag = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=35,
        pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$",
    ),
]


def utc_now() -> datetime:
    """Return an aware UTC timestamp for entity creation and updates."""

    return datetime.now(timezone.utc)


class VerificationStatus(StrEnum):
    """Confidence state for a fact or the authenticity of a source record."""

    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


class SourceType(StrEnum):
    """Origin category used to preserve provenance without inferring authority."""

    OFFICIAL_RESULT = "OFFICIAL_RESULT"
    OFFICIAL_FEDERATION_RESULT = "OFFICIAL_FEDERATION_RESULT"
    OFFICIAL_COMPETITION_SYSTEM = "OFFICIAL_COMPETITION_SYSTEM"
    OFFICIAL_COMPETITION_DOCUMENT = "OFFICIAL_COMPETITION_DOCUMENT"
    CLUB_DOCUMENT = "CLUB_DOCUMENT"
    PROFESSIONAL_MESSAGE = "PROFESSIONAL_MESSAGE"
    SCREENSHOT = "SCREENSHOT"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    OTHER_UNVERIFIED = "OTHER_UNVERIFIED"
    FEDERATION_PUBLICATION = "FEDERATION_PUBLICATION"
    COMPETITION_ORGANIZER = "COMPETITION_ORGANIZER"
    ATHLETE_PROVIDED = "ATHLETE_PROVIDED"
    PROFESSIONAL_FEEDBACK = "PROFESSIONAL_FEEDBACK"
    MESSAGE = "MESSAGE"
    DOCUMENT = "DOCUMENT"
    MEDIA = "MEDIA"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class ResultStatus(StrEnum):
    """Outcome state for a recorded result."""

    COMPLETED = "COMPLETED"
    DID_NOT_START = "DID_NOT_START"
    DID_NOT_FINISH = "DID_NOT_FINISH"
    DISQUALIFIED = "DISQUALIFIED"
    UNKNOWN = "UNKNOWN"


class MessageDirection(StrEnum):
    """Direction relative to the Athlete Context system."""

    INBOUND = "INBOUND"
    OUTGOING = "OUTGOING"
    UNKNOWN = "UNKNOWN"


class DocumentType(StrEnum):
    """Broad document classification without parsing its contents."""

    OFFICIAL = "OFFICIAL"
    REPORT = "REPORT"
    CERTIFICATE = "CERTIFICATE"
    CORRESPONDENCE = "CORRESPONDENCE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class DomainModel(BaseModel):
    """Strict base configuration shared by all domain models."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Entity(DomainModel):
    """Base fields for independently identified domain records."""

    id: UUID = Field(default_factory=uuid4)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        return self


class FactualRecord(Entity):
    """A fact candidate with explicit verification and provenance references."""

    verification_status: VerificationStatus
    source_ids: list[UUID] = Field(min_length=1)

    @field_validator("source_ids")
    @classmethod
    def require_unique_sources(cls, source_ids: list[UUID]) -> list[UUID]:
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_ids must be unique")
        return source_ids


class SourceRecord(Entity):
    """Uninterpreted source material; verification applies only to authenticity."""

    source_id: UUID
    original_language: LanguageTag | None = Field(
        ..., description="Known BCP 47-style tag, or None when explicitly unknown"
    )
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    verification_scope: Literal["record_authenticity"] = "record_authenticity"


class Source(Entity):
    """Provenance for a fact or source record."""

    original_source: NonEmptyText
    source_type: SourceType
    captured_at: AwareDatetime
    original_language: LanguageTag | None = Field(
        ..., description="Known BCP 47-style tag, or None when explicitly unknown"
    )
    source_reference: NonEmptyText | None = Field(
        ..., description="External identifier, or None when explicitly unavailable"
    )
    source_url: AnyUrl | None = Field(
        ..., description="Original URL, or None when the source has no URL"
    )
    published_at: AwareDatetime | None = None
    verification_status: VerificationStatus


class Athlete(FactualRecord):
    """Athlete identity and known biographical context."""

    display_name: NonEmptyText
    given_name: NonEmptyText | None = None
    family_name: NonEmptyText | None = None
    birth_date: date | None = None
    nationality: NonEmptyText | None = None
    primary_language: LanguageTag | None = None


class Competition(FactualRecord):
    """Competition metadata without monitoring or ingestion behavior."""

    name: NonEmptyText
    start_date: date | None = None
    end_date: date | None = None
    location: NonEmptyText | None = None
    category: NonEmptyText | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class Event(FactualRecord):
    """A discipline or category contested within one competition."""

    competition_id: UUID
    name: NonEmptyText
    discipline: NonEmptyText | None = None
    category: NonEmptyText | None = None
    scheduled_at: AwareDatetime | None = None


class Result(FactualRecord):
    """A performance result with direct athlete, competition, event, and source links."""

    athlete_id: UUID
    competition_id: UUID
    event_id: UUID
    source_id: UUID
    status: ResultStatus
    performance_value: Decimal | None = Field(default=None, ge=0)
    performance_unit: NonEmptyText | None = None
    placing: int | None = Field(default=None, ge=1)
    recorded_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_performance(self) -> Self:
        if self.source_id not in self.source_ids:
            raise ValueError("source_id must also be present in source_ids")
        if (self.performance_value is None) != (self.performance_unit is None):
            raise ValueError(
                "performance_value and performance_unit must be provided together"
            )
        if self.status == ResultStatus.COMPLETED and self.performance_value is None:
            raise ValueError("completed results require a performance value and unit")
        return self


class Standard(FactualRecord):
    """An event standard qualified by optional age, category, and context."""

    event_id: UUID
    name: NonEmptyText
    value: Decimal = Field(ge=0)
    unit: NonEmptyText
    minimum_age: int | None = Field(default=None, ge=0)
    maximum_age: int | None = Field(default=None, ge=0)
    category: NonEmptyText | None = None
    context: dict[NonEmptyText, NonEmptyText] = Field(default_factory=dict)
    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if (
            self.minimum_age is not None
            and self.maximum_age is not None
            and self.maximum_age < self.minimum_age
        ):
            raise ValueError("maximum_age must not be lower than minimum_age")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not be earlier than valid_from")
        return self


class Message(SourceRecord):
    """Original message content retained as a source record."""

    sender: NonEmptyText
    recipient: NonEmptyText | None = None
    content: NonEmptyText
    sent_at: AwareDatetime
    direction: MessageDirection = MessageDirection.UNKNOWN
    athlete_id: UUID | None = None


class Document(SourceRecord):
    """Original document metadata/content retained without parsing."""

    title: NonEmptyText
    document_type: DocumentType = DocumentType.UNKNOWN
    content: NonEmptyText | None = None
    storage_reference: NonEmptyText | None = None
    issued_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def require_content_or_reference(self) -> Self:
        if self.content is None and self.storage_reference is None:
            raise ValueError("document requires content or storage_reference")
        return self


class ProfessionalFeedback(SourceRecord):
    """Professional observations retained separately from verified facts."""

    athlete_id: UUID
    professional_name: NonEmptyText
    professional_role: NonEmptyText | None = None
    content: NonEmptyText
    provided_at: AwareDatetime
    competition_id: UUID | None = None
    event_id: UUID | None = None
    result_id: UUID | None = None


class FederationUpdate(SourceRecord):
    """Federation publication retained without monitoring or interpretation."""

    federation_name: NonEmptyText
    title: NonEmptyText
    content: NonEmptyText
    published_at: AwareDatetime | None = None
    effective_at: AwareDatetime | None = None
    affected_event_ids: list[UUID] = Field(default_factory=list)

    @field_validator("affected_event_ids")
    @classmethod
    def require_unique_events(cls, event_ids: list[UUID]) -> list[UUID]:
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("affected_event_ids must be unique")
        return event_ids


class ResultTrace(DomainModel):
    """Validated in-memory relationship context for a result and its provenance."""

    athlete: Athlete
    competition: Competition
    event: Event
    source: Source
    result: Result

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        if self.event.competition_id != self.competition.id:
            raise ValueError("event does not belong to the supplied competition")
        if self.result.athlete_id != self.athlete.id:
            raise ValueError("result does not belong to the supplied athlete")
        if self.result.competition_id != self.competition.id:
            raise ValueError("result does not belong to the supplied competition")
        if self.result.event_id != self.event.id:
            raise ValueError("result does not belong to the supplied event")
        if self.result.source_id != self.source.id:
            raise ValueError("result does not reference the supplied source")
        return self
