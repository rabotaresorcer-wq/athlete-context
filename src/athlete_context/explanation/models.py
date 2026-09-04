"""Structured inputs and traceable outputs for deterministic explanations."""

from __future__ import annotations

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from athlete_context.analytics import (
    ConsistencyResult,
    HistoricalPbDelta,
    PerformanceDelta,
    ProgressionPoint,
    StandardGap,
    TrendResult,
)
from athlete_context.competition import MonitoredFederationUpdate, PlannedCompetition
from athlete_context.context_linking import ContextLinkResult
from athlete_context.domain import (
    HistoricalResult,
    ProfessionalFeedback,
    Source,
    SourceType,
    VerificationStatus,
)
from athlete_context.domain.models import DomainModel
from athlete_context.input_processing import LanguageCode


class ExplanationType(StrEnum):
    RESULT_SUMMARY = "RESULT_SUMMARY"
    PROGRESSION_SUMMARY = "PROGRESSION_SUMMARY"
    STANDARD_CONTEXT = "STANDARD_CONTEXT"
    COMPETITION_UPDATE = "COMPETITION_UPDATE"
    SOURCE_VERIFICATION_NOTICE = "SOURCE_VERIFICATION_NOTICE"
    CONFLICT_NOTICE = "CONFLICT_NOTICE"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class ExplanationStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class AnalyticsExplanationContext(DomainModel):
    """Already-computed Layer 3 values accepted without recalculation."""

    progression: list[ProgressionPoint] = Field(default_factory=list)
    delta_to_previous: PerformanceDelta | None = None
    delta_to_historical_pb: HistoricalPbDelta | None = None
    standard_gap: StandardGap | None = None
    trend: TrendResult | None = None
    consistency: ConsistencyResult | None = None


class CompetitionExplanationContext(DomainModel):
    planned_competition: PlannedCompetition | None = None
    federation_update: MonitoredFederationUpdate | None = None

    @model_validator(mode="after")
    def require_competition_context(self) -> Self:
        if self.planned_competition is None and self.federation_update is None:
            raise ValueError("competition context requires a plan or update")
        return self


class SupportingFact(DomainModel):
    text: str
    source_ids: list[UUID] = Field(default_factory=list)
    verification_status: VerificationStatus

    @field_validator("text")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("supporting fact text must not be blank")
        return value

    @field_validator("source_ids")
    @classmethod
    def require_unique_sources(cls, values: list[UUID]) -> list[UUID]:
        if len(values) != len(set(values)):
            raise ValueError("supporting fact source_ids must be unique")
        return values


class ExplanationSourceReference(DomainModel):
    source_id: UUID
    original_source: str
    source_type: SourceType
    source_reference: str | None = None
    source_url: str | None = None
    captured_at: AwareDatetime
    original_language: str | None
    verification_status: VerificationStatus


class ExplanationContext(DomainModel):
    explanation_type: ExplanationType
    athlete_id: UUID | None = None
    result_id: UUID | None = None
    competition_id: UUID | None = None
    event_id: UUID | None = None
    historical_result: HistoricalResult | None = None
    context_link: ContextLinkResult | None = None
    analytics: AnalyticsExplanationContext | None = None
    standard_context: StandardGap | None = None
    competition_context: CompetitionExplanationContext | None = None
    source_provenance: list[Source] = Field(default_factory=list)
    verification_status: VerificationStatus
    professional_feedback: list[ProfessionalFeedback] = Field(default_factory=list)
    language: LanguageCode = LanguageCode.UNKNOWN
    unresolved_items: list[str] = Field(default_factory=list)

    @field_validator("source_provenance")
    @classmethod
    def require_unique_sources(cls, values: list[Source]) -> list[Source]:
        source_ids = [source.id for source in values]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_provenance IDs must be unique")
        return values

    @field_validator("unresolved_items")
    @classmethod
    def require_unique_unresolved_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("unresolved_items must not contain blank values")
        if len(values) != len(set(values)):
            raise ValueError("unresolved_items must be unique")
        return values


class ExplanationResult(DomainModel):
    status: ExplanationStatus
    explanation_type: ExplanationType
    summary: str | None = None
    supporting_facts: list[SupportingFact] = Field(default_factory=list)
    verification_note: str | None = None
    unresolved_items: list[str] = Field(default_factory=list)
    source_references: list[ExplanationSourceReference] = Field(default_factory=list)
    language: LanguageCode

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.status == ExplanationStatus.AVAILABLE:
            if self.summary is None or self.verification_note is None:
                raise ValueError(
                    "available explanation requires summary and verification_note"
                )
        return self
