"""Models for approved competition lifecycles and event-scoped monitoring."""

from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, JsonValue, field_validator, model_validator

from athlete_context.domain import Competition, FederationUpdate
from athlete_context.domain.models import DomainModel, utc_now


class CompetitionLifecycleStatus(StrEnum):
    PLANNED = "PLANNED"
    MONITORING = "MONITORING"
    REGISTRATION_INFO_AVAILABLE = "REGISTRATION_INFO_AVAILABLE"
    START_DETAILS_AVAILABLE = "START_DETAILS_AVAILABLE"
    COMPLETED_AWAITING_RESULT = "COMPLETED_AWAITING_RESULT"
    OFFICIAL_RESULT_AVAILABLE = "OFFICIAL_RESULT_AVAILABLE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class CompetitionMonitoringStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class FederationUpdateType(StrEnum):
    REGULATION = "REGULATION"
    ELIGIBILITY_OR_REQUIREMENTS = "ELIGIBILITY_OR_REQUIREMENTS"
    REGISTRATION_DEADLINE = "REGISTRATION_DEADLINE"
    SCHEDULE = "SCHEDULE"
    START_LIST = "START_LIST"
    RESULT = "RESULT"
    CANCELLATION = "CANCELLATION"
    OTHER = "OTHER"


class MonitoringCheckType(StrEnum):
    REGULATION_CHECK = "REGULATION_CHECK"
    REQUIREMENTS_CHECK = "REQUIREMENTS_CHECK"
    DEADLINE_CHECK = "DEADLINE_CHECK"
    START_DETAILS_CHECK = "START_DETAILS_CHECK"
    RESULT_CHECK = "RESULT_CHECK"


class MonitoringPhase(StrEnum):
    BEFORE_COMPETITION = "BEFORE_COMPETITION"
    NEAR_START = "NEAR_START"
    AFTER_COMPETITION = "AFTER_COMPETITION"


class MonitoringCheckStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CONFLICT = "CONFLICT"
    CANCELLED = "CANCELLED"


class MonitoringPolicy(DomainModel):
    """Configurable offsets without federation-specific scheduling assumptions."""

    regulation_days_before: int = Field(default=60, ge=0)
    requirements_days_before: int = Field(default=45, ge=0)
    deadline_days_before: int = Field(default=30, ge=0)
    start_details_days_before: int = Field(default=7, ge=0)
    result_delay_hours: int = Field(default=6, ge=0)


class PlannedCompetition(DomainModel):
    """A competition explicitly approved outside Athlete Context."""

    competition: Competition
    approved: Literal[True]
    federation_source_reference: str | None = None
    lifecycle_status: CompetitionLifecycleStatus = CompetitionLifecycleStatus.PLANNED
    monitoring_status: CompetitionMonitoringStatus = (
        CompetitionMonitoringStatus.NOT_STARTED
    )
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @field_validator("federation_source_reference")
    @classmethod
    def validate_reference(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError(
                "federation_source_reference must contain non-whitespace content"
            )
        return value

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        return self

    @property
    def competition_id(self) -> UUID:
        return self.competition.id

    @property
    def name(self) -> str:
        return self.competition.name

    @property
    def start_date(self) -> date | None:
        return self.competition.start_date

    @property
    def end_date(self) -> date | None:
        return self.competition.end_date


class MonitoredFederationUpdate(FederationUpdate):
    """Federation source record scoped to one approved competition."""

    competition_id: UUID
    update_type: FederationUpdateType
    captured_at: AwareDatetime
    payload: dict[str, JsonValue] | None = None
    update_reference: str | None = None

    @field_validator("update_reference")
    @classmethod
    def validate_update_reference(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("update_reference must contain non-whitespace content")
        return value


class MonitoringCheck(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    competition_id: UUID
    check_type: MonitoringCheckType
    phase: MonitoringPhase
    relative_time: timedelta
    status: MonitoringCheckStatus = MonitoringCheckStatus.PENDING
    last_checked_at: AwareDatetime | None = None
    next_check_at: AwareDatetime | None = None
    update_ids: list[UUID] = Field(default_factory=list)

    @field_validator("update_ids")
    @classmethod
    def require_unique_updates(cls, update_ids: list[UUID]) -> list[UUID]:
        if len(update_ids) != len(set(update_ids)):
            raise ValueError("update_ids must be unique")
        return update_ids


class CompetitionMonitoringPlan(DomainModel):
    competition_id: UUID
    checks: list[MonitoringCheck] = Field(default_factory=list)
    updates: list[MonitoredFederationUpdate] = Field(default_factory=list)
    has_conflicts: bool = False
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_scope_and_timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        if any(check.competition_id != self.competition_id for check in self.checks):
            raise ValueError("all checks must belong to the plan competition")
        if any(update.competition_id != self.competition_id for update in self.updates):
            raise ValueError("all updates must belong to the plan competition")
        check_types = [check.check_type for check in self.checks]
        if len(check_types) != len(set(check_types)):
            raise ValueError("monitoring check types must be unique within a plan")
        return self
