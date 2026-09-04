"""Deterministic tests for Layer 3 historical performance analytics."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from athlete_context.analytics import (
    ConsistencyStatus,
    HistoricalPerformanceAnalytics,
    TrendStatus,
)
from athlete_context.domain import (
    HistoricalResult,
    HistoricalResultStatus,
    PoolLength,
    RoundType,
    Source,
    SourceType,
    Standard,
    StandardStatus,
    Stroke,
    VerificationStatus,
    format_swim_time,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
ATHLETE_ID = UUID("50000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("50000000-0000-0000-0000-000000000002")
OTHER_EVENT_ID = UUID("50000000-0000-0000-0000-000000000003")


def make_result(
    number: int,
    day: int,
    time_centiseconds: int | None,
    *,
    athlete_id: UUID = ATHLETE_ID,
    event_id: UUID = EVENT_ID,
    distance_m: int = 100,
    stroke: Stroke = Stroke.FREESTYLE,
    pool_length: PoolLength = PoolLength.SCM_25M,
    result_status: HistoricalResultStatus = HistoricalResultStatus.OFFICIAL,
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
) -> HistoricalResult:
    result_id = UUID(f"51000000-0000-0000-0000-{number:012d}")
    source_id = UUID(f"52000000-0000-0000-0000-{number:012d}")
    return HistoricalResult(
        id=result_id,
        athlete_id=athlete_id,
        competition_id=UUID(f"53000000-0000-0000-0000-{number:012d}"),
        event_id=event_id,
        swim_date=date(2026, 1, day),
        round=RoundType.FINAL,
        heat_number=1,
        lane=4,
        distance_m=distance_m,
        stroke=stroke,
        pool_length=pool_length,
        official_time_raw=(
            format_swim_time(time_centiseconds)
            if time_centiseconds is not None
            else None
        ),
        official_time_centiseconds=time_centiseconds,
        splits=[],
        aqua_points=None,
        standard_status=StandardStatus.UNKNOWN,
        result_status=result_status,
        verification_status=verification_status,
        source_id=source_id,
        source_ids=[source_id],
        created_at=NOW,
        updated_at=NOW,
    )


def make_source(result: HistoricalResult) -> Source:
    return Source(
        id=result.source_id,
        original_source=f"Synthetic analytics source {result.id}",
        source_type=SourceType.OFFICIAL_FEDERATION_RESULT,
        captured_at=NOW,
        original_language="en",
        source_reference=f"analytics-{result.id}",
        source_url=f"https://example.test/analytics/{result.id}",
        verification_status=VerificationStatus.VERIFIED,
        created_at=NOW,
        updated_at=NOW,
    )


def make_standard(
    value: str,
    *,
    event_id: UUID = EVENT_ID,
    unit: str = "seconds",
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
) -> Standard:
    source_id = UUID("54000000-0000-0000-0000-000000000001")
    return Standard(
        id=UUID("54000000-0000-0000-0000-000000000002"),
        event_id=event_id,
        name="Synthetic applicable standard",
        value=Decimal(value),
        unit=unit,
        verification_status=verification_status,
        source_ids=[source_id],
        created_at=NOW,
        updated_at=NOW,
    )


def test_personal_best_from_multiple_comparable_results() -> None:
    results = [
        make_result(1, 1, 7000),
        make_result(2, 5, 6800),
        make_result(3, 10, 6900),
    ]
    analytics = HistoricalPerformanceAnalytics(results)

    personal_best = analytics.personal_best(results[0])

    assert personal_best is not None
    assert personal_best.result_id == results[1].id
    assert personal_best.official_time_centiseconds == 6800


def test_result_progression_is_chronological_and_preserves_provenance() -> None:
    later = make_result(4, 10, 6800)
    earlier = make_result(5, 1, 7000)
    sources = [make_source(earlier), make_source(later)]
    analytics = HistoricalPerformanceAnalytics([later, earlier], sources=sources)

    progression = analytics.result_progression(earlier)

    assert [point.result_id for point in progression] == [earlier.id, later.id]
    assert progression[0].competition_id == earlier.competition_id
    assert progression[0].source_id == earlier.source_id
    assert progression[0].source_reference == f"analytics-{earlier.id}"
    assert progression[0].source_url == f"https://example.test/analytics/{earlier.id}"


def test_delta_to_previous_uses_documented_sign_convention() -> None:
    previous = make_result(6, 1, 6800)
    target = make_result(7, 5, 6900)
    analytics = HistoricalPerformanceAnalytics([target, previous])

    delta = analytics.delta_to_previous(target)

    assert delta.available is True
    assert delta.comparison_result_id == previous.id
    assert delta.delta_centiseconds == 100
    assert delta.delta_percent == Decimal("1.4706")


def test_delta_to_historical_pb_uses_only_earlier_results() -> None:
    first = make_result(8, 1, 7000)
    previous_pb = make_result(9, 5, 6800)
    target = make_result(10, 10, 6900)
    analytics = HistoricalPerformanceAnalytics([target, first, previous_pb])

    delta = analytics.delta_to_historical_pb(target)

    assert delta.available is True
    assert delta.previous_pb_result_id == previous_pb.id
    assert delta.previous_pb_time == 6800
    assert delta.delta_centiseconds == 100
    assert delta.delta_percent == Decimal("1.4706")
    assert delta.new_pb is False


def test_new_pb_detection() -> None:
    previous_pb = make_result(11, 1, 7000)
    target = make_result(12, 5, 6800)
    analytics = HistoricalPerformanceAnalytics([previous_pb, target])

    delta = analytics.delta_to_historical_pb(target)

    assert delta.previous_pb_time == 7000
    assert delta.delta_centiseconds == -200
    assert delta.delta_percent == Decimal("-2.8571")
    assert delta.new_pb is True


def test_later_pb_does_not_affect_earlier_historical_pb_delta() -> None:
    first = make_result(13, 1, 7000)
    target = make_result(14, 5, 6800)
    later_pb = make_result(15, 10, 6600)
    analytics = HistoricalPerformanceAnalytics([later_pb, target, first])

    delta = analytics.delta_to_historical_pb(target)

    assert delta.previous_pb_time == 7000
    assert delta.delta_centiseconds == -200
    assert delta.new_pb is True


def test_pb_progression_contains_only_new_records() -> None:
    results = [
        make_result(16, 1, 7000),
        make_result(17, 5, 6800),
        make_result(18, 10, 6900),
        make_result(19, 15, 6700),
    ]
    analytics = HistoricalPerformanceAnalytics(results)

    progression = analytics.pb_progression(results[0])

    assert [point.official_time_centiseconds for point in progression] == [
        7000,
        6800,
        6700,
    ]


def test_short_and_long_course_analytics_remain_separate() -> None:
    short_course = make_result(20, 1, 7000, pool_length=PoolLength.SCM_25M)
    long_course = make_result(21, 5, 6500, pool_length=PoolLength.LCM_50M)
    analytics = HistoricalPerformanceAnalytics([short_course, long_course])

    personal_best = analytics.personal_best(short_course)

    assert personal_best is not None
    assert personal_best.result_id == short_course.id


def test_different_events_remain_separate() -> None:
    reference = make_result(22, 1, 7000)
    other_event = make_result(23, 5, 6500, event_id=OTHER_EVENT_ID)
    analytics = HistoricalPerformanceAnalytics([reference, other_event])

    progression = analytics.result_progression(reference)

    assert [point.result_id for point in progression] == [reference.id]


@pytest.mark.parametrize(
    ("status", "verification_status"),
    [
        (HistoricalResultStatus.DNS, VerificationStatus.VERIFIED),
        (HistoricalResultStatus.DNF, VerificationStatus.VERIFIED),
        (HistoricalResultStatus.DISQUALIFIED, VerificationStatus.VERIFIED),
        (HistoricalResultStatus.UNKNOWN, VerificationStatus.UNKNOWN),
    ],
)
def test_non_performance_statuses_are_excluded(
    status: HistoricalResultStatus,
    verification_status: VerificationStatus,
) -> None:
    valid = make_result(24, 1, 7000)
    excluded = make_result(
        25,
        5,
        None,
        result_status=status,
        verification_status=verification_status,
    )
    analytics = HistoricalPerformanceAnalytics([valid, excluded])

    assert [point.result_id for point in analytics.result_progression(valid)] == [
        valid.id
    ]


def test_conflict_is_excluded_from_canonical_analytics() -> None:
    valid = make_result(26, 1, 7000)
    conflict = make_result(
        27, 5, 6500, verification_status=VerificationStatus.CONFLICT
    )
    analytics = HistoricalPerformanceAnalytics([valid, conflict])

    personal_best = analytics.personal_best(valid)

    assert personal_best is not None
    assert personal_best.result_id == valid.id


def test_conflict_can_be_included_only_when_explicitly_requested() -> None:
    valid = make_result(28, 1, 7000)
    conflict = make_result(
        29, 5, 6500, verification_status=VerificationStatus.CONFLICT
    )
    analytics = HistoricalPerformanceAnalytics(
        [valid, conflict], include_conflicts=True
    )

    personal_best = analytics.personal_best(valid)

    assert personal_best is not None
    assert personal_best.result_id == conflict.id


def test_standard_gap_passed() -> None:
    result = make_result(30, 1, 6000)
    analytics = HistoricalPerformanceAnalytics([result])

    gap = analytics.standard_gap(result, make_standard("61.00"))

    assert gap.available is True
    assert gap.result_time_centiseconds == 6000
    assert gap.standard_time_centiseconds == 6100
    assert gap.gap_centiseconds == -100
    assert gap.gap_percent == Decimal("-1.6393")
    assert gap.passed is True


def test_standard_gap_not_passed() -> None:
    result = make_result(31, 1, 6200)
    analytics = HistoricalPerformanceAnalytics([result])

    gap = analytics.standard_gap(result, make_standard("61.00"))

    assert gap.available is True
    assert gap.gap_centiseconds == 100
    assert gap.gap_percent == Decimal("1.6393")
    assert gap.passed is False


def test_missing_standard_is_unavailable() -> None:
    result = make_result(32, 1, 6200)
    analytics = HistoricalPerformanceAnalytics([result])

    gap = analytics.standard_gap(result, None)

    assert gap.available is False
    assert gap.standard_time_centiseconds is None
    assert gap.passed is None
    assert gap.reason == "no applicable standard supplied"


@pytest.mark.parametrize(
    ("times", "expected"),
    [
        ([7000, 6900, 6800], TrendStatus.IMPROVING),
        ([7000, 7020, 6990], TrendStatus.STABLE),
        ([6800, 6900, 7000], TrendStatus.DECLINING),
    ],
)
def test_trend_classification(
    times: list[int], expected: TrendStatus
) -> None:
    results = [
        make_result(40 + index, index + 1, value)
        for index, value in enumerate(times)
    ]
    analytics = HistoricalPerformanceAnalytics(results)

    trend = analytics.trend(results[0])

    assert trend.status == expected
    assert trend.sample_size == 3


def test_trend_insufficient_data() -> None:
    results = [make_result(50, 1, 7000), make_result(51, 2, 6900)]
    analytics = HistoricalPerformanceAnalytics(results)

    trend = analytics.trend(results[0])

    assert trend.status == TrendStatus.INSUFFICIENT_DATA
    assert trend.sample_size == 2


def test_consistency_calculation() -> None:
    results = [
        make_result(52, 1, 5900),
        make_result(53, 2, 6000),
        make_result(54, 3, 6100),
    ]
    analytics = HistoricalPerformanceAnalytics(results)

    consistency = analytics.consistency(results[0])

    assert consistency.status == ConsistencyStatus.AVAILABLE
    assert consistency.sample_size == 3
    assert consistency.mean_centiseconds == Decimal("6000.0000")
    assert consistency.range_centiseconds == 200
    assert consistency.standard_deviation_centiseconds == Decimal("81.6497")
    assert consistency.coefficient_of_variation_percent == Decimal("1.3608")


def test_consistency_insufficient_data() -> None:
    results = [make_result(55, 1, 6000), make_result(56, 2, 6100)]
    analytics = HistoricalPerformanceAnalytics(results)

    consistency = analytics.consistency(results[0])

    assert consistency.status == ConsistencyStatus.INSUFFICIENT_DATA
    assert consistency.sample_size == 2
    assert consistency.mean_centiseconds is None


def test_analytics_do_not_modify_historical_results() -> None:
    results = [
        make_result(57, 1, 7000),
        make_result(58, 2, 6900),
        make_result(59, 3, 6800),
    ]
    before = [result.model_dump() for result in results]
    analytics = HistoricalPerformanceAnalytics(results)

    analytics.personal_best(results[0])
    analytics.delta_to_previous(results[-1])
    analytics.delta_to_historical_pb(results[-1])
    analytics.pb_progression(results[0])
    analytics.trend(results[0])
    analytics.consistency(results[0])

    assert [result.model_dump() for result in results] == before
