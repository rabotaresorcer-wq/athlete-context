"""Deterministic creation and due-time evaluation of monitoring plans."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from athlete_context.competition.models import (
    CompetitionMonitoringPlan,
    MonitoringCheck,
    MonitoringCheckStatus,
    MonitoringCheckType,
    MonitoringPhase,
    MonitoringPolicy,
    PlannedCompetition,
)


def _utc_day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _check_id(competition_id: UUID, check_type: MonitoringCheckType) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"athlete-context:{competition_id}:{check_type.value}",
    )


def create_monitoring_plan(
    competition: PlannedCompetition,
    policy: MonitoringPolicy | None = None,
) -> CompetitionMonitoringPlan:
    """Build an event-scoped plan for an already-approved competition."""

    if not isinstance(competition, PlannedCompetition):
        raise TypeError("competition must be an approved PlannedCompetition")
    policy = policy or MonitoringPolicy()
    checks: list[MonitoringCheck] = []
    if competition.start_date is not None:
        start = _utc_day_start(competition.start_date)
        end_date = competition.end_date or competition.start_date
        after_end = _utc_day_start(end_date + timedelta(days=1))
        definitions = (
            (
                MonitoringCheckType.REGULATION_CHECK,
                MonitoringPhase.BEFORE_COMPETITION,
                timedelta(days=-policy.regulation_days_before),
                start - timedelta(days=policy.regulation_days_before),
            ),
            (
                MonitoringCheckType.REQUIREMENTS_CHECK,
                MonitoringPhase.BEFORE_COMPETITION,
                timedelta(days=-policy.requirements_days_before),
                start - timedelta(days=policy.requirements_days_before),
            ),
            (
                MonitoringCheckType.DEADLINE_CHECK,
                MonitoringPhase.BEFORE_COMPETITION,
                timedelta(days=-policy.deadline_days_before),
                start - timedelta(days=policy.deadline_days_before),
            ),
            (
                MonitoringCheckType.START_DETAILS_CHECK,
                MonitoringPhase.NEAR_START,
                timedelta(days=-policy.start_details_days_before),
                start - timedelta(days=policy.start_details_days_before),
            ),
            (
                MonitoringCheckType.RESULT_CHECK,
                MonitoringPhase.AFTER_COMPETITION,
                timedelta(days=1, hours=policy.result_delay_hours),
                after_end + timedelta(hours=policy.result_delay_hours),
            ),
        )
        checks = [
            MonitoringCheck(
                id=_check_id(competition.competition_id, check_type),
                competition_id=competition.competition_id,
                check_type=check_type,
                phase=phase,
                relative_time=relative_time,
                next_check_at=next_check_at,
            )
            for check_type, phase, relative_time, next_check_at in definitions
        ]

    return CompetitionMonitoringPlan(
        competition_id=competition.competition_id,
        checks=checks,
        created_at=competition.updated_at,
        updated_at=competition.updated_at,
    )


def get_due_checks(
    plan: CompetitionMonitoringPlan,
    now: datetime,
) -> tuple[MonitoringCheck, ...]:
    """Return pending checks whose deterministic time has arrived."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return tuple(
        check
        for check in plan.checks
        if check.status == MonitoringCheckStatus.PENDING
        and check.next_check_at is not None
        and check.next_check_at <= now
    )
