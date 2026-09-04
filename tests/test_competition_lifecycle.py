"""Deterministic tests for Layer 6 competition lifecycle and monitoring."""

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from athlete_context.competition import (
    CompetitionLifecycleStatus,
    CompetitionMonitoringStatus,
    CompetitionMonitoringPlan,
    FederationUpdateType,
    MonitoredFederationUpdate,
    MonitoringCheckStatus,
    MonitoringCheckType,
    MonitoringCheck,
    MonitoringPolicy,
    PlannedCompetition,
    advance_competition_lifecycle,
    create_monitoring_plan,
    get_due_checks,
    record_monitoring_update,
)
from athlete_context.context_linking import (
    ContextLinkResult,
    LinkStatus,
    RecordType,
)
from athlete_context.domain import (
    Competition,
    HistoricalResult,
    HistoricalResultStatus,
    PoolLength,
    RoundType,
    StandardStatus,
    Stroke,
    VerificationStatus,
)
from athlete_context.input_processing import (
    ContentType,
    LanguageCode,
    TranslationStatus,
)

NOW = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
START_DATE = date(2026, 11, 10)
END_DATE = date(2026, 11, 12)
COMPETITION_ID = UUID("81000000-0000-0000-0000-000000000001")
OTHER_COMPETITION_ID = UUID("81000000-0000-0000-0000-000000000002")
SOURCE_ID = UUID("81000000-0000-0000-0000-000000000003")
ATHLETE_ID = UUID("81000000-0000-0000-0000-000000000004")
EVENT_ID = UUID("81000000-0000-0000-0000-000000000005")
INPUT_ID = UUID("81000000-0000-0000-0000-000000000006")


def make_competition(
    *,
    competition_id: UUID = COMPETITION_ID,
    start_date: date | None = START_DATE,
    end_date: date | None = END_DATE,
) -> Competition:
    return Competition(
        id=competition_id,
        name="Synthetic Approved Competition",
        start_date=start_date,
        end_date=end_date,
        verification_status=VerificationStatus.VERIFIED,
        source_ids=[SOURCE_ID],
        created_at=NOW,
        updated_at=NOW,
    )


def make_planned_competition(
    *,
    competition: Competition | None = None,
) -> PlannedCompetition:
    return PlannedCompetition(
        competition=competition or make_competition(),
        approved=True,
        federation_source_reference="federation:synthetic-competition",
        created_at=NOW,
        updated_at=NOW,
    )


def make_update(
    update_type: FederationUpdateType,
    *,
    number: int,
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
    competition_id: UUID = COMPETITION_ID,
    source_id: UUID = SOURCE_ID,
) -> MonitoredFederationUpdate:
    captured_at = datetime(2026, 10, 1, 10, number, tzinfo=timezone.utc)
    return MonitoredFederationUpdate(
        id=UUID(f"82000000-0000-0000-0000-{number:012d}"),
        source_id=source_id,
        original_language="tr",
        verification_status=verification_status,
        federation_name="Synthetic Federation",
        title=f"Synthetic {update_type.value} update",
        content="Synthetic official-source content",
        published_at=captured_at - timedelta(hours=1),
        competition_id=competition_id,
        update_type=update_type,
        captured_at=captured_at,
        payload={"category": update_type.value},
        update_reference=f"update:{number}",
        created_at=captured_at,
        updated_at=captured_at,
    )


def get_check(
    plan: CompetitionMonitoringPlan,
    check_type: MonitoringCheckType,
) -> MonitoringCheck:
    return next(check for check in plan.checks if check.check_type == check_type)


def test_planned_competition_creates_monitoring_plan() -> None:
    competition = make_planned_competition()

    plan = create_monitoring_plan(competition)

    assert plan.competition_id == COMPETITION_ID
    assert len(plan.checks) == 5
    assert {check.check_type for check in plan.checks} == set(MonitoringCheckType)


def test_competition_is_never_auto_selected() -> None:
    with pytest.raises(ValidationError):
        PlannedCompetition(
            competition=make_competition(),
            approved=False,
            created_at=NOW,
            updated_at=NOW,
        )

    with pytest.raises(TypeError):
        create_monitoring_plan(make_competition())


def test_regulation_check_becomes_due_before_start() -> None:
    plan = create_monitoring_plan(make_planned_competition())
    due_at = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)

    due = get_due_checks(plan, due_at)

    assert MonitoringCheckType.REGULATION_CHECK in {
        check.check_type for check in due
    }


def test_deadline_check_becomes_due_before_start() -> None:
    plan = create_monitoring_plan(make_planned_competition())
    due_at = datetime(2026, 10, 11, 0, 0, tzinfo=timezone.utc)

    due = get_due_checks(plan, due_at)

    assert MonitoringCheckType.DEADLINE_CHECK in {
        check.check_type for check in due
    }


def test_start_details_check_becomes_due_near_start() -> None:
    plan = create_monitoring_plan(make_planned_competition())
    due_at = datetime(2026, 11, 3, 0, 0, tzinfo=timezone.utc)

    due = get_due_checks(plan, due_at)

    assert MonitoringCheckType.START_DETAILS_CHECK in {
        check.check_type for check in due
    }


def test_result_check_becomes_due_after_competition() -> None:
    plan = create_monitoring_plan(make_planned_competition())
    due_at = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)

    due = get_due_checks(plan, due_at)

    assert MonitoringCheckType.RESULT_CHECK in {check.check_type for check in due}


def test_checks_are_not_due_too_early() -> None:
    plan = create_monitoring_plan(make_planned_competition())
    too_early = datetime(2026, 9, 10, 23, 59, tzinfo=timezone.utc)

    assert get_due_checks(plan, too_early) == ()


def test_custom_policy_changes_dates_deterministically() -> None:
    policy = MonitoringPolicy(
        regulation_days_before=10,
        requirements_days_before=9,
        deadline_days_before=8,
        start_details_days_before=2,
        result_delay_hours=12,
    )

    first = create_monitoring_plan(make_planned_competition(), policy)
    second = create_monitoring_plan(make_planned_competition(), policy)

    assert first == second
    assert get_check(
        first,
        MonitoringCheckType.REGULATION_CHECK,
    ).next_check_at == datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)


def test_missing_competition_date_is_handled_safely() -> None:
    competition = make_planned_competition(
        competition=make_competition(start_date=None, end_date=None)
    )

    plan = create_monitoring_plan(competition)
    advanced = advance_competition_lifecycle(competition, plan, NOW)

    assert plan.checks == []
    assert advanced.lifecycle_status == CompetitionLifecycleStatus.PLANNED
    assert advanced.monitoring_status == CompetitionMonitoringStatus.NOT_STARTED


def test_regulation_update_is_recorded() -> None:
    competition = make_planned_competition()
    plan = create_monitoring_plan(competition)
    update = make_update(FederationUpdateType.REGULATION, number=1)

    recorded = record_monitoring_update(plan, update)
    advanced = advance_competition_lifecycle(
        competition,
        recorded,
        update.captured_at,
    )

    assert recorded.updates == [update]
    assert get_check(
        recorded,
        MonitoringCheckType.REGULATION_CHECK,
    ).status == MonitoringCheckStatus.COMPLETED
    assert advanced.lifecycle_status == (
        CompetitionLifecycleStatus.REGISTRATION_INFO_AVAILABLE
    )


def test_schedule_update_is_recorded() -> None:
    competition = make_planned_competition()
    update = make_update(FederationUpdateType.SCHEDULE, number=2)
    plan = record_monitoring_update(create_monitoring_plan(competition), update)

    advanced = advance_competition_lifecycle(
        competition,
        plan,
        update.captured_at,
    )

    assert update in plan.updates
    assert advanced.lifecycle_status == (
        CompetitionLifecycleStatus.START_DETAILS_AVAILABLE
    )


def test_start_list_update_is_recorded() -> None:
    update = make_update(FederationUpdateType.START_LIST, number=3)
    plan = record_monitoring_update(
        create_monitoring_plan(make_planned_competition()),
        update,
    )

    check = get_check(plan, MonitoringCheckType.START_DETAILS_CHECK)

    assert check.status == MonitoringCheckStatus.COMPLETED
    assert check.update_ids == [update.id]


def test_verified_official_result_update_advances_lifecycle() -> None:
    competition = make_planned_competition()
    update = make_update(FederationUpdateType.RESULT, number=4)
    plan = record_monitoring_update(create_monitoring_plan(competition), update)

    advanced = advance_competition_lifecycle(
        competition,
        plan,
        datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc),
    )

    assert advanced.lifecycle_status == (
        CompetitionLifecycleStatus.OFFICIAL_RESULT_AVAILABLE
    )
    assert advanced.lifecycle_status != CompetitionLifecycleStatus.CLOSED


def test_unverified_result_does_not_close_competition() -> None:
    competition = make_planned_competition()
    update = make_update(
        FederationUpdateType.RESULT,
        number=5,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    plan = record_monitoring_update(create_monitoring_plan(competition), update)

    advanced = advance_competition_lifecycle(
        competition,
        plan,
        datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc),
    )

    assert advanced.lifecycle_status == (
        CompetitionLifecycleStatus.COMPLETED_AWAITING_RESULT
    )
    assert get_check(
        plan,
        MonitoringCheckType.RESULT_CHECK,
    ).status == MonitoringCheckStatus.PENDING


def test_cancelled_competition_lifecycle() -> None:
    competition = make_planned_competition()
    update = make_update(FederationUpdateType.CANCELLATION, number=6)
    plan = record_monitoring_update(create_monitoring_plan(competition), update)

    advanced = advance_competition_lifecycle(
        competition,
        plan,
        update.captured_at,
    )

    assert advanced.lifecycle_status == CompetitionLifecycleStatus.CANCELLED
    assert advanced.monitoring_status == CompetitionMonitoringStatus.CANCELLED
    assert all(
        check.status == MonitoringCheckStatus.CANCELLED for check in plan.checks
    )


def test_conflicting_federation_update_is_preserved() -> None:
    update = make_update(
        FederationUpdateType.RESULT,
        number=7,
        verification_status=VerificationStatus.CONFLICT,
    )
    plan = record_monitoring_update(
        create_monitoring_plan(make_planned_competition()),
        update,
    )

    assert plan.updates == [update]
    assert plan.has_conflicts is True
    assert get_check(
        plan,
        MonitoringCheckType.RESULT_CHECK,
    ).status == MonitoringCheckStatus.CONFLICT


def test_repeated_update_is_idempotent() -> None:
    update = make_update(FederationUpdateType.REGULATION, number=8)
    original = create_monitoring_plan(make_planned_competition())

    first = record_monitoring_update(original, update)
    second = record_monitoring_update(first, update)

    assert first == second
    assert len(second.updates) == 1
    assert len(
        get_check(second, MonitoringCheckType.REGULATION_CHECK).update_ids
    ) == 1


def test_lower_quality_update_does_not_override_verified_update() -> None:
    verified = make_update(FederationUpdateType.SCHEDULE, number=9)
    unverified = make_update(
        FederationUpdateType.SCHEDULE,
        number=10,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    original = create_monitoring_plan(make_planned_competition())

    after_verified = record_monitoring_update(original, verified)
    after_unverified = record_monitoring_update(after_verified, unverified)

    assert after_unverified.updates == [verified, unverified]
    assert get_check(
        after_unverified,
        MonitoringCheckType.START_DETAILS_CHECK,
    ).status == MonitoringCheckStatus.COMPLETED


def test_monitoring_remains_competition_scoped() -> None:
    plan = create_monitoring_plan(make_planned_competition())
    wrong_update = make_update(
        FederationUpdateType.REGULATION,
        number=11,
        competition_id=OTHER_COMPETITION_ID,
    )

    with pytest.raises(ValueError, match="different competition"):
        record_monitoring_update(plan, wrong_update)

    assert all(check.competition_id == COMPETITION_ID for check in plan.checks)
    assert plan.updates == []


def make_historical_result(
    verification_status: VerificationStatus,
) -> HistoricalResult:
    return HistoricalResult(
        id=UUID("83000000-0000-0000-0000-000000000001"),
        athlete_id=ATHLETE_ID,
        competition_id=COMPETITION_ID,
        event_id=EVENT_ID,
        swim_date=END_DATE,
        round=RoundType.FINAL,
        distance_m=100,
        stroke=Stroke.FREESTYLE,
        pool_length=PoolLength.SCM_25M,
        official_time_raw="59.50",
        official_time_centiseconds=5950,
        standard_status=StandardStatus.UNKNOWN,
        result_status=HistoricalResultStatus.OFFICIAL,
        verification_status=verification_status,
        source_id=SOURCE_ID,
        source_ids=[SOURCE_ID],
        created_at=NOW,
        updated_at=NOW,
    )


def make_context_link() -> ContextLinkResult:
    return ContextLinkResult(
        input_id=INPUT_ID,
        source_id=SOURCE_ID,
        captured_at=NOW,
        content_type=ContentType.STRUCTURED_DATA,
        record_type=RecordType.RESULT,
        athlete_id=ATHLETE_ID,
        competition_id=COMPETITION_ID,
        event_id=EVENT_ID,
        link_status=LinkStatus.LINKED,
        matched_references={
            "athlete_id": ATHLETE_ID,
            "competition_id": COMPETITION_ID,
            "event_id": EVENT_ID,
        },
        verification_status=VerificationStatus.UNVERIFIED,
        original_language=LanguageCode.UNKNOWN,
        translation_status=TranslationStatus.NOT_REQUIRED,
    )


def test_layer_2_verification_rules_are_not_bypassed() -> None:
    competition = make_planned_competition()
    update = make_update(FederationUpdateType.RESULT, number=12)
    plan = record_monitoring_update(create_monitoring_plan(competition), update)

    advanced = advance_competition_lifecycle(
        competition,
        plan,
        datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc),
        historical_result=make_historical_result(VerificationStatus.UNVERIFIED),
        context_link=make_context_link(),
    )

    assert advanced.lifecycle_status == (
        CompetitionLifecycleStatus.OFFICIAL_RESULT_AVAILABLE
    )
    assert advanced.lifecycle_status != CompetitionLifecycleStatus.CLOSED


def test_verified_linked_historical_result_can_close_lifecycle() -> None:
    competition = make_planned_competition()
    update = make_update(FederationUpdateType.RESULT, number=13)
    plan = record_monitoring_update(create_monitoring_plan(competition), update)

    advanced = advance_competition_lifecycle(
        competition,
        plan,
        datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc),
        historical_result=make_historical_result(VerificationStatus.VERIFIED),
        context_link=make_context_link(),
    )

    assert advanced.lifecycle_status == CompetitionLifecycleStatus.CLOSED
    assert advanced.monitoring_status == CompetitionMonitoringStatus.COMPLETED


def test_update_provenance_is_preserved() -> None:
    update = make_update(FederationUpdateType.REGULATION, number=14)

    plan = record_monitoring_update(
        create_monitoring_plan(make_planned_competition()),
        update,
    )
    preserved = plan.updates[0]

    assert preserved.source_id == SOURCE_ID
    assert preserved.original_language == "tr"
    assert preserved.captured_at == update.captured_at
    assert preserved.published_at == update.published_at
    assert preserved.update_reference == "update:14"
    assert preserved.payload == {"category": "REGULATION"}
