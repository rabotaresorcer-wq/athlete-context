"""Deterministic, read-only analytics over stored historical swim results."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from athlete_context.domain.historical_results import (
    HistoricalResult,
    ResultStatus,
)
from athlete_context.domain.models import (
    DomainModel,
    Source,
    Standard,
    VerificationStatus,
)

_DECIMAL_QUANTUM = Decimal("0.0001")
_TREND_MINIMUM_RESULTS = 3
_CONSISTENCY_MINIMUM_RESULTS = 3
_STABLE_TOLERANCE_PERCENT = Decimal("0.5000")


class TrendStatus(StrEnum):
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DECLINING = "DECLINING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ConsistencyStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ProgressionPoint(DomainModel):
    result_id: UUID
    date: date
    official_time_centiseconds: int = Field(gt=0)
    competition_id: UUID
    source_id: UUID
    source_reference: str | None = None
    source_url: str | None = None


class PerformanceDelta(DomainModel):
    available: bool
    target_result_id: UUID
    comparison_result_id: UUID | None = None
    delta_centiseconds: int | None = None
    delta_percent: Decimal | None = None
    reason: str | None = None


class HistoricalPbDelta(DomainModel):
    available: bool
    target_result_id: UUID
    previous_pb_result_id: UUID | None = None
    previous_pb_time: int | None = None
    delta_centiseconds: int | None = None
    delta_percent: Decimal | None = None
    new_pb: bool
    reason: str | None = None


class StandardGap(DomainModel):
    available: bool
    result_id: UUID
    standard_id: UUID | None = None
    result_time_centiseconds: int | None = None
    standard_time_centiseconds: int | None = None
    gap_centiseconds: int | None = None
    gap_percent: Decimal | None = None
    passed: bool | None = None
    reason: str | None = None


class TrendResult(DomainModel):
    status: TrendStatus
    requested_window: int = Field(ge=2)
    sample_size: int = Field(ge=0)
    start_time_centiseconds: int | None = None
    end_time_centiseconds: int | None = None
    change_centiseconds: int | None = None
    change_percent: Decimal | None = None


class ConsistencyResult(DomainModel):
    status: ConsistencyStatus
    requested_window: int = Field(ge=2)
    sample_size: int = Field(ge=0)
    mean_centiseconds: Decimal | None = None
    range_centiseconds: int | None = None
    standard_deviation_centiseconds: Decimal | None = None
    coefficient_of_variation_percent: Decimal | None = None


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_DECIMAL_QUANTUM)


def _percent(delta: int | Decimal, baseline: int | Decimal) -> Decimal:
    baseline_decimal = Decimal(baseline)
    if baseline_decimal == 0:
        raise ValueError("percentage baseline must not be zero")
    return _quantize(Decimal(delta) * Decimal(100) / baseline_decimal)


def _chronology_key(result: HistoricalResult) -> tuple[object, ...]:
    return (result.swim_date, result.created_at, str(result.id))


def _comparable(left: HistoricalResult, right: HistoricalResult) -> bool:
    return (
        left.athlete_id == right.athlete_id
        and left.event_id == right.event_id
        and left.distance_m == right.distance_m
        and left.stroke == right.stroke
        and left.pool_length == right.pool_length
    )


class HistoricalPerformanceAnalytics:
    """Read-only calculations over an immutable snapshot of historical results."""

    def __init__(
        self,
        results: Iterable[HistoricalResult],
        *,
        sources: Iterable[Source] = (),
        include_conflicts: bool = False,
    ) -> None:
        self._results = tuple(results)
        self._sources = {source.id: source for source in sources}
        self._include_conflicts = include_conflicts

    def _is_eligible(self, result: HistoricalResult) -> bool:
        if result.official_time_centiseconds is None:
            return False
        if result.result_status != ResultStatus.OFFICIAL:
            return False
        if result.verification_status == VerificationStatus.CONFLICT:
            return self._include_conflicts
        return result.verification_status == VerificationStatus.VERIFIED

    def _comparable_results(
        self, reference: HistoricalResult
    ) -> tuple[HistoricalResult, ...]:
        return tuple(
            sorted(
                (
                    result
                    for result in self._results
                    if _comparable(result, reference) and self._is_eligible(result)
                ),
                key=_chronology_key,
            )
        )

    def _point(self, result: HistoricalResult) -> ProgressionPoint:
        source = self._sources.get(result.source_id)
        return ProgressionPoint(
            result_id=result.id,
            date=result.swim_date,
            official_time_centiseconds=result.official_time_centiseconds,
            competition_id=result.competition_id,
            source_id=result.source_id,
            source_reference=(source.source_reference if source else None),
            source_url=(str(source.source_url) if source and source.source_url else None),
        )

    def personal_best(self, reference: HistoricalResult) -> ProgressionPoint | None:
        """Return the fastest verified official comparable result."""

        results = self._comparable_results(reference)
        if not results:
            return None
        best = min(
            results,
            key=lambda result: (
                result.official_time_centiseconds,
                _chronology_key(result),
            ),
        )
        return self._point(best)

    def result_progression(
        self, reference: HistoricalResult
    ) -> tuple[ProgressionPoint, ...]:
        """Return comparable canonical results in deterministic chronological order."""

        return tuple(
            self._point(result) for result in self._comparable_results(reference)
        )

    def delta_to_previous(self, target: HistoricalResult) -> PerformanceDelta:
        """Compare a target with the latest comparable result from an earlier date."""

        if not self._is_eligible(target):
            return PerformanceDelta(
                available=False,
                target_result_id=target.id,
                reason="target is not an eligible verified official timed result",
            )
        previous = [
            result
            for result in self._comparable_results(target)
            if result.swim_date < target.swim_date
        ]
        if not previous:
            return PerformanceDelta(
                available=False,
                target_result_id=target.id,
                reason="no previous comparable result",
            )
        comparison = previous[-1]
        delta = (
            target.official_time_centiseconds
            - comparison.official_time_centiseconds
        )
        return PerformanceDelta(
            available=True,
            target_result_id=target.id,
            comparison_result_id=comparison.id,
            delta_centiseconds=delta,
            delta_percent=_percent(delta, comparison.official_time_centiseconds),
        )

    def delta_to_historical_pb(self, target: HistoricalResult) -> HistoricalPbDelta:
        """Compare a target only with the PB established on an earlier date."""

        if not self._is_eligible(target):
            return HistoricalPbDelta(
                available=False,
                target_result_id=target.id,
                new_pb=False,
                reason="target is not an eligible verified official timed result",
            )
        previous = [
            result
            for result in self._comparable_results(target)
            if result.swim_date < target.swim_date
        ]
        if not previous:
            return HistoricalPbDelta(
                available=True,
                target_result_id=target.id,
                new_pb=True,
                reason="first eligible comparable result",
            )
        previous_pb = min(
            previous,
            key=lambda result: (
                result.official_time_centiseconds,
                _chronology_key(result),
            ),
        )
        delta = (
            target.official_time_centiseconds
            - previous_pb.official_time_centiseconds
        )
        return HistoricalPbDelta(
            available=True,
            target_result_id=target.id,
            previous_pb_result_id=previous_pb.id,
            previous_pb_time=previous_pb.official_time_centiseconds,
            delta_centiseconds=delta,
            delta_percent=_percent(delta, previous_pb.official_time_centiseconds),
            new_pb=delta < 0,
        )

    def pb_progression(
        self, reference: HistoricalResult
    ) -> tuple[ProgressionPoint, ...]:
        """Return only swims that established a strictly faster historical PB."""

        progression: list[ProgressionPoint] = []
        best_time: int | None = None
        for result in self._comparable_results(reference):
            if best_time is None or result.official_time_centiseconds < best_time:
                progression.append(self._point(result))
                best_time = result.official_time_centiseconds
        return tuple(progression)

    def standard_gap(
        self, result: HistoricalResult, standard: Standard | None
    ) -> StandardGap:
        """Compare with one explicitly supplied, verified, event-compatible standard."""

        if not self._is_eligible(result):
            return StandardGap(
                available=False,
                result_id=result.id,
                reason="result is not an eligible verified official timed result",
            )
        if standard is None:
            return StandardGap(
                available=False,
                result_id=result.id,
                reason="no applicable standard supplied",
            )
        if standard.event_id != result.event_id:
            return StandardGap(
                available=False,
                result_id=result.id,
                standard_id=standard.id,
                reason="supplied standard belongs to a different event",
            )
        if standard.verification_status != VerificationStatus.VERIFIED:
            return StandardGap(
                available=False,
                result_id=result.id,
                standard_id=standard.id,
                reason="supplied standard is not verified",
            )

        standard_time = self._standard_centiseconds(standard)
        if standard_time is None:
            return StandardGap(
                available=False,
                result_id=result.id,
                standard_id=standard.id,
                reason="standard time unit or precision is unsupported",
            )

        result_time = result.official_time_centiseconds
        gap = result_time - standard_time
        return StandardGap(
            available=True,
            result_id=result.id,
            standard_id=standard.id,
            result_time_centiseconds=result_time,
            standard_time_centiseconds=standard_time,
            gap_centiseconds=gap,
            gap_percent=_percent(gap, standard_time),
            passed=gap <= 0,
        )

    @staticmethod
    def _standard_centiseconds(standard: Standard) -> int | None:
        unit = standard.unit.casefold()
        if unit in {"second", "seconds", "s"}:
            value = standard.value * Decimal(100)
        elif unit in {"centisecond", "centiseconds", "cs"}:
            value = standard.value
        else:
            return None
        if value <= 0 or value != value.to_integral_value():
            return None
        return int(value)

    def trend(
        self, reference: HistoricalResult, *, window: int = 5
    ) -> TrendResult:
        """Classify first-to-last change using a ±0.5% stable tolerance."""

        if window < 2:
            raise ValueError("trend window must be at least 2")
        recent = self._comparable_results(reference)[-window:]
        if len(recent) < _TREND_MINIMUM_RESULTS:
            return TrendResult(
                status=TrendStatus.INSUFFICIENT_DATA,
                requested_window=window,
                sample_size=len(recent),
            )

        start = recent[0].official_time_centiseconds
        end = recent[-1].official_time_centiseconds
        change = end - start
        change_percent = _percent(change, start)
        if change_percent < -_STABLE_TOLERANCE_PERCENT:
            status = TrendStatus.IMPROVING
        elif change_percent > _STABLE_TOLERANCE_PERCENT:
            status = TrendStatus.DECLINING
        else:
            status = TrendStatus.STABLE
        return TrendResult(
            status=status,
            requested_window=window,
            sample_size=len(recent),
            start_time_centiseconds=start,
            end_time_centiseconds=end,
            change_centiseconds=change,
            change_percent=change_percent,
        )

    def consistency(
        self, reference: HistoricalResult, *, window: int = 5
    ) -> ConsistencyResult:
        """Return range, mean, population deviation, and coefficient of variation."""

        if window < 2:
            raise ValueError("consistency window must be at least 2")
        recent = self._comparable_results(reference)[-window:]
        if len(recent) < _CONSISTENCY_MINIMUM_RESULTS:
            return ConsistencyResult(
                status=ConsistencyStatus.INSUFFICIENT_DATA,
                requested_window=window,
                sample_size=len(recent),
            )

        times = [Decimal(result.official_time_centiseconds) for result in recent]
        sample_size = len(times)
        mean = sum(times) / Decimal(sample_size)
        variance = sum((value - mean) ** 2 for value in times) / Decimal(sample_size)
        standard_deviation = variance.sqrt()
        return ConsistencyResult(
            status=ConsistencyStatus.AVAILABLE,
            requested_window=window,
            sample_size=sample_size,
            mean_centiseconds=_quantize(mean),
            range_centiseconds=int(max(times) - min(times)),
            standard_deviation_centiseconds=_quantize(standard_deviation),
            coefficient_of_variation_percent=_percent(standard_deviation, mean),
        )
