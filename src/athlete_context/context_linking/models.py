"""Models for deterministic links between normalized input and known entities."""

from __future__ import annotations

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, field_validator, model_validator

from athlete_context.domain import VerificationStatus
from athlete_context.domain.models import DomainModel
from athlete_context.input_processing import (
    ContentType,
    LanguageCode,
    TranslationStatus,
)


class RecordType(StrEnum):
    RESULT = "RESULT"
    STANDARD = "STANDARD"
    MESSAGE = "MESSAGE"
    DOCUMENT = "DOCUMENT"
    PROFESSIONAL_FEEDBACK = "PROFESSIONAL_FEEDBACK"
    FEDERATION_UPDATE = "FEDERATION_UPDATE"
    UNKNOWN = "UNKNOWN"


class LinkStatus(StrEnum):
    LINKED = "LINKED"
    PARTIALLY_LINKED = "PARTIALLY_LINKED"
    UNRESOLVED = "UNRESOLVED"
    CONFLICT = "CONFLICT"


class EntityType(StrEnum):
    ATHLETE = "ATHLETE"
    COMPETITION = "COMPETITION"
    EVENT = "EVENT"


class ExactReference(DomainModel):
    """One exact external reference associated with one known domain entity."""

    entity_type: EntityType
    reference: str
    entity_id: UUID

    @field_validator("reference")
    @classmethod
    def require_nonblank_reference(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reference must contain non-whitespace content")
        return value


class ContextLinkResult(DomainModel):
    """Source-preserving outcome of exact, non-verifying context resolution."""

    input_id: UUID
    source_id: UUID
    captured_at: AwareDatetime
    content_type: ContentType
    record_type: RecordType
    athlete_id: UUID | None = None
    competition_id: UUID | None = None
    event_id: UUID | None = None
    link_status: LinkStatus
    matched_references: dict[str, UUID] = Field(default_factory=dict)
    unresolved_references: dict[str, str] = Field(default_factory=dict)
    verification_status: VerificationStatus
    original_text: str | None = None
    original_language: LanguageCode
    translated_text: str | None = None
    target_language: LanguageCode | None = None
    translation_status: TranslationStatus
    structured_data: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def enforce_verification_boundary(self) -> Self:
        if self.verification_status == VerificationStatus.VERIFIED:
            raise ValueError("context linking cannot verify source information")
        if self.link_status == LinkStatus.CONFLICT:
            if self.verification_status != VerificationStatus.CONFLICT:
                raise ValueError(
                    "conflicting links require CONFLICT verification status"
                )
        elif self.verification_status == VerificationStatus.CONFLICT:
            raise ValueError("CONFLICT verification status requires conflicting links")
        return self
