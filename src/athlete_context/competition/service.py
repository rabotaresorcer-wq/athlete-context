"""Lifecycle orchestration for approved, event-scoped competition monitoring."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from athlete_context.competition.models import (
    CompetitionLifecycleStatus,
    CompetitionMonitoringPlan,
    CompetitionMonitoringStatus,
    FederationUpdateType,
    MonitoredFederationUpdate,
    MonitoringCheck,
    MonitoringCheckStatus,
    MonitoringCheckType,
    PlannedCompetition,
)
from athlete_context.context_linking import (
    ContextLinkResult,
    LinkStatus,
    RecordType,
)
from athlete_context.domain import (
    HistoricalResult,
    HistoricalResultStatus,
    VerificationStatus,
)

_UPDATE_CHECK_TYPES: dict[FederationUpdateType, tuple[MonitoringCheckType, ...]] = {
    FederationUpdateType.REGULATION: (MonitoringCheckType.REGULATION_CHECK,),
    FederationUpdateType.ELIGIBILITY_OR_REQUIREMENTS: (
        MonitoringCheckType.REQUIREMENTS_CHECK,
    ),
    FederationUpdateType.REGISTRATION_DEADLINE: (
        MonitoringCheckType.DEADLINE_CHECK,
    ),
    FederationUpdateType.SCHEDULE: (MonitoringCheckType.START_DETAILS_CHECK,),
    FederationUpdateType.START_LIST: (MonitoringCheckType.START_DETAILS_CHECK,),
    FederationUpdateType.RESULT: (MonitoringCheckType.RESULT_CHECK,),
}

_STATUS_PRIORITY = {
    CompetitionLifecycleStatus.UNKNOWN: 0,
    CompetitionLifecycleStatus.PLANNED: 1,
    CompetitionLifecycleStatus.MONITORING: 2,
    CompetitionLifecycleStatus.REGISTRATION_INFO_AVAILABLE: 3,
    CompetitionLifecycleStatus.START_DETAILS_AVAILABLE: 4,
    CompetitionLifecycleStatus.COMPLETED_AWAITING_RESULT: 5,
    CompetitionLifecycleStatus.OFFICIAL_RESULT_AVAILABLE: 6,
    CompetitionLifecycleStatus.CLOSED: 7,
}


def record_monitoring_update(
    plan: CompetitionMonitoringPlan,
    federation_update: MonitoredFederationUpdate,
) -> CompetitionMonitoringPlan:
    """Append an update without replacing earlier or higher-confidence records."""

    if federation_update.competition_id != plan.competition_id:
        raise ValueError("federation update belongs to a different competition")
    if any(existing == federation_update for existing in plan.updates):
        return plan

    same_id_conflict = any(
        existing.id == federation_update.id and existing != federation_update
        for existing in plan.updates
    )
    explicit_conflict = (
        federation_update.verification_status == VerificationStatus.CONFLICT
    )
    affected_types = _UPDATE_CHECK_TYPES.get(federation_update.update_type, ())
    checks = [
        _record_check_update(
            check,
            federation_update,
            affected=(
                check.check_type in affected_types
                or federation_update.update_type
                == FederationUpdateType.CANCELLATION
            ),
            conflict=same_id_conflict or explicit_conflict,
        )
        for check in plan.checks
    ]
    if (
        federation_update.update_type == FederationUpdateType.CANCELLATION
        and federation_update.verification_status == VerificationStatus.VERIFIED
    ):
        checks = [
            check.model_copy(
                update={
                    "status": MonitoringCheckStatus.CANCELLED,
                    "last_checked_at": federation_update.captured_at,
                }
            )
            for check in checks
        ]

    return plan.model_copy(
        update={
            "checks": checks,
            "updates": [*plan.updates, federation_update.model_copy(deep=True)],
            "has_conflicts": (
                plan.has_conflicts or same_id_conflict or explicit_conflict
            ),
            "updated_at": max(plan.updated_at, federation_update.captured_at),
        },
        deep=True,
    )


def _record_check_update(
    check: MonitoringCheck,
    federation_update: MonitoredFederationUpdate,
    *,
    affected: bool,
    conflict: bool,
) -> MonitoringCheck:
    if not affected:
        return check.model_copy(deep=True)
    update_ids = list(check.update_ids)
    if federation_update.id not in update_ids:
        update_ids.append(federation_update.id)
    values: dict[str, object] = {
        "last_checked_at": federation_update.captured_at,
        "update_ids": update_ids,
    }
    if conflict:
        values["status"] = MonitoringCheckStatus.CONFLICT
    elif federation_update.verification_status == VerificationStatus.VERIFIED:
        values["status"] = MonitoringCheckStatus.COMPLETED
    return check.model_copy(update=values, deep=True)


def advance_competition_lifecycle(
    competition: PlannedCompetition,
    plan: CompetitionMonitoringPlan,
    now: datetime,
    *,
    historical_result: HistoricalResult | None = None,
    context_link: ContextLinkResult | None = None,
) -> PlannedCompetition:
    """Advance lifecycle only from dates and explicit verified earlier-layer data."""

    if plan.competition_id != competition.competition_id:
        raise ValueError("monitoring plan belongs to a different competition")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if (historical_result is None) != (context_link is None):
        raise ValueError(
            "historical_result and context_link must be supplied together"
        )
    if competition.lifecycle_status in {
        CompetitionLifecycleStatus.CANCELLED,
        CompetitionLifecycleStatus.CLOSED,
    }:
        return competition

    verified_updates = [
        update
        for update in plan.updates
        if update.verification_status == VerificationStatus.VERIFIED
    ]
    conflict_types = {
        update.update_type
        for update in plan.updates
        if update.verification_status == VerificationStatus.CONFLICT
    }
    if any(
        update.update_type == FederationUpdateType.CANCELLATION
        for update in verified_updates
    ) and FederationUpdateType.CANCELLATION not in conflict_types:
        return _with_status(
            competition,
            CompetitionLifecycleStatus.CANCELLED,
            CompetitionMonitoringStatus.CANCELLED,
            now,
        )

    candidate = (
        CompetitionLifecycleStatus.MONITORING
        if plan.checks
        else CompetitionLifecycleStatus.PLANNED
    )
    registration_types = {
        FederationUpdateType.REGULATION,
        FederationUpdateType.ELIGIBILITY_OR_REQUIREMENTS,
        FederationUpdateType.REGISTRATION_DEADLINE,
    }
    if any(update.update_type in registration_types for update in verified_updates):
        candidate = _later_status(
            candidate,
            CompetitionLifecycleStatus.REGISTRATION_INFO_AVAILABLE,
        )
    if any(
        update.update_type
        in {FederationUpdateType.SCHEDULE, FederationUpdateType.START_LIST}
        for update in verified_updates
    ):
        candidate = _later_status(
            candidate,
            CompetitionLifecycleStatus.START_DETAILS_AVAILABLE,
        )

    if _competition_has_ended(competition, now):
        candidate = _later_status(
            candidate,
            CompetitionLifecycleStatus.COMPLETED_AWAITING_RESULT,
        )
    verified_result_update = any(
        update.update_type == FederationUpdateType.RESULT
        for update in verified_updates
    ) and FederationUpdateType.RESULT not in conflict_types
    if verified_result_update:
        candidate = _later_status(
            candidate,
            CompetitionLifecycleStatus.OFFICIAL_RESULT_AVAILABLE,
        )
    if (
        verified_result_update
        and historical_result is not None
        and context_link is not None
        and _is_valid_result_handoff(
            competition,
            historical_result,
            context_link,
            verified_updates,
        )
    ):
        candidate = CompetitionLifecycleStatus.CLOSED

    candidate = _later_status(competition.lifecycle_status, candidate)
    monitoring_status = (
        CompetitionMonitoringStatus.COMPLETED
        if candidate
        in {
            CompetitionLifecycleStatus.OFFICIAL_RESULT_AVAILABLE,
            CompetitionLifecycleStatus.CLOSED,
        }
        else (
            CompetitionMonitoringStatus.ACTIVE
            if plan.checks
            else CompetitionMonitoringStatus.NOT_STARTED
        )
    )
    return _with_status(competition, candidate, monitoring_status, now)


def _competition_has_ended(
    competition: PlannedCompetition,
    now: datetime,
) -> bool:
    if competition.start_date is None:
        return False
    end_date = competition.end_date or competition.start_date
    end_boundary = datetime.combine(
        end_date + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )
    return now >= end_boundary


def _is_valid_result_handoff(
    competition: PlannedCompetition,
    historical_result: HistoricalResult,
    context_link: ContextLinkResult,
    verified_updates: list[MonitoredFederationUpdate],
) -> bool:
    return (
        historical_result.competition_id == competition.competition_id
        and historical_result.result_status == HistoricalResultStatus.OFFICIAL
        and historical_result.verification_status == VerificationStatus.VERIFIED
        and context_link.record_type == RecordType.RESULT
        and context_link.link_status == LinkStatus.LINKED
        and context_link.athlete_id == historical_result.athlete_id
        and context_link.competition_id == historical_result.competition_id
        and context_link.event_id == historical_result.event_id
        and any(
            update.update_type == FederationUpdateType.RESULT
            and update.source_id == historical_result.source_id
            for update in verified_updates
        )
    )


def _later_status(
    left: CompetitionLifecycleStatus,
    right: CompetitionLifecycleStatus,
) -> CompetitionLifecycleStatus:
    if left in {
        CompetitionLifecycleStatus.CANCELLED,
        CompetitionLifecycleStatus.CLOSED,
    }:
        return left
    return left if _STATUS_PRIORITY[left] >= _STATUS_PRIORITY[right] else right


def _with_status(
    competition: PlannedCompetition,
    lifecycle_status: CompetitionLifecycleStatus,
    monitoring_status: CompetitionMonitoringStatus,
    now: datetime,
) -> PlannedCompetition:
    if (
        competition.lifecycle_status == lifecycle_status
        and competition.monitoring_status == monitoring_status
    ):
        return competition
    return competition.model_copy(
        update={
            "lifecycle_status": lifecycle_status,
            "monitoring_status": monitoring_status,
            "updated_at": max(competition.updated_at, now),
        },
        deep=True,
    )
