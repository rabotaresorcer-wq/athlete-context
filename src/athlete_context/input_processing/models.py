"""Validated input-processing records for source-preserving normalization."""

from __future__ import annotations

from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, JsonValue, field_validator, model_validator

from athlete_context.domain.models import DomainModel


class ContentType(StrEnum):
    MESSAGE = "MESSAGE"
    DOCUMENT_TEXT = "DOCUMENT_TEXT"
    STRUCTURED_DATA = "STRUCTURED_DATA"
    UNKNOWN = "UNKNOWN"


class LanguageCode(StrEnum):
    EN = "EN"
    RU = "RU"
    TR = "TR"
    UNKNOWN = "UNKNOWN"


class TranslationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    TRANSLATED = "TRANSLATED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class RawInput(DomainModel):
    """Source input that is already available as text or structured data."""

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    content_type: ContentType = ContentType.UNKNOWN
    raw_text: str | None = None
    structured_data: dict[str, JsonValue] | None = Field(default=None, min_length=1)
    original_language: LanguageCode | None = None
    captured_at: AwareDatetime

    @field_validator("raw_text")
    @classmethod
    def require_nonblank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("raw_text must contain non-whitespace content")
        return value

    @model_validator(mode="after")
    def validate_content(self) -> Self:
        if self.raw_text is None and self.structured_data is None:
            raise ValueError("raw input requires text or structured data")
        if self.content_type in {ContentType.MESSAGE, ContentType.DOCUMENT_TEXT}:
            if self.raw_text is None:
                raise ValueError(f"{self.content_type} input requires raw_text")
        if (
            self.content_type == ContentType.STRUCTURED_DATA
            and self.structured_data is None
        ):
            raise ValueError("STRUCTURED_DATA input requires structured_data")
        return self


class NormalizedInput(DomainModel):
    """Derived input view that retains original content and translation state."""

    input_id: UUID
    source_id: UUID
    content_type: ContentType
    original_text: str | None
    original_language: LanguageCode
    translated_text: str | None = None
    target_language: LanguageCode | None = None
    structured_data: dict[str, JsonValue] | None = None
    translation_status: TranslationStatus
    captured_at: AwareDatetime

    @field_validator("original_text", "translated_text")
    @classmethod
    def require_nonblank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("text must contain non-whitespace content")
        return value

    @model_validator(mode="after")
    def validate_translation_state(self) -> Self:
        if self.translation_status == TranslationStatus.TRANSLATED:
            if self.translated_text is None or self.target_language is None:
                raise ValueError(
                    "translated input requires translated_text and target_language"
                )
            if self.original_text is None:
                raise ValueError("translated input requires original_text")
        elif self.translated_text is not None:
            raise ValueError("translated_text is only valid for TRANSLATED status")
        return self
