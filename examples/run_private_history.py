"""Run private structured result history through the Athlete Context pipeline."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from athlete_context.analytics import HistoricalPerformanceAnalytics
from athlete_context.domain import HistoricalResult
from athlete_context.explanation import (
    AnalyticsExplanationContext,
    ExplanationContext,
    ExplanationType,
    generate_explanation,
)
from athlete_context.imports import OfficialResultImport, OfficialResultImportService
from athlete_context.input_processing import LanguageCode
from athlete_context.services import (
    HistoricalResultIngestService,
    InMemoryHistoricalResultRepository,
    IngestOutcomeStatus,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DATA_DIR = REPOSITORY_ROOT / "data" / "private"


class PrivateHistoryRunError(RuntimeError):
    """Safe user-facing error for controlled private history runs."""


@dataclass(frozen=True)
class DisciplineHistorySummary:
    """Minimal Russian-report data for one comparable discipline group."""

    discipline: str
    canonical_results: int
    analytics_points: int
    latest_result_id: str
    latest_date: str
    latest_time: str
    verification_status: str
    personal_best_time: str | None
    trend_status: str
    result_summary: str
    progression_summary: str | None


@dataclass(frozen=True)
class PrivateHistoryRunReport:
    """Concise non-payload output from one private history run."""

    imported_items: int
    canonical_results: int
    duplicate_items: int
    conflict_items: int
    disciplines: list[DisciplineHistorySummary]


def resolve_private_history_path(
    supplied_path: str | Path,
    *,
    private_data_dir: Path = PRIVATE_DATA_DIR,
    repository_root: Path = REPOSITORY_ROOT,
) -> Path:
    """Return an existing history file only when it is inside data/private."""

    path = Path(supplied_path).expanduser()
    if not path.is_absolute():
        path = repository_root / path
    resolved = path.resolve(strict=False)
    private_root = private_data_dir.resolve(strict=False)
    if not resolved.is_relative_to(private_root):
        raise PrivateHistoryRunError("private history path must be inside data/private/")
    if not resolved.is_file():
        raise PrivateHistoryRunError("private history file does not exist")
    return resolved


def load_private_history_imports(
    path: str | Path,
    *,
    private_data_dir: Path = PRIVATE_DATA_DIR,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[OfficialResultImport]:
    """Load and validate private history JSON without printing its payload."""

    private_path = resolve_private_history_path(
        path,
        private_data_dir=private_data_dir,
        repository_root=repository_root,
    )
    try:
        raw: Any = json.loads(private_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PrivateHistoryRunError("private history file is not valid JSON") from error
    except OSError as error:
        raise PrivateHistoryRunError("private history file could not be read") from error
    if not isinstance(raw, dict):
        raise PrivateHistoryRunError("private history JSON must be an object")

    results = raw.get("results")
    if not isinstance(results, list) or not results:
        raise PrivateHistoryRunError("private history JSON requires non-empty results")

    imports: list[OfficialResultImport] = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            raise PrivateHistoryRunError(
                f"private history result at index {index} must be an object"
            )
        try:
            imports.append(OfficialResultImport.model_validate(item))
        except ValidationError as error:
            raise PrivateHistoryRunError(
                "private history JSON failed OfficialResultImport validation "
                f"at results[{index}]"
            ) from error
    return imports


def run_private_history(
    path: str | Path,
    *,
    private_data_dir: Path = PRIVATE_DATA_DIR,
    repository_root: Path = REPOSITORY_ROOT,
) -> PrivateHistoryRunReport:
    """Execute local-only import, ingestion, analytics and Russian reporting."""

    imports = load_private_history_imports(
        path,
        private_data_dir=private_data_dir,
        repository_root=repository_root,
    )
    import_service = OfficialResultImportService()
    repository = InMemoryHistoricalResultRepository()
    ingest_service = HistoricalResultIngestService(repository)
    sources = []
    outcomes = []

    for result_import in imports:
        try:
            mapping = import_service.map_import(result_import)
        except ValueError as error:
            raise PrivateHistoryRunError(str(error)) from error
        outcome = ingest_service.ingest(mapping.structured_result, source=mapping.source)
        if outcome.record is None:
            raise PrivateHistoryRunError(
                f"private history result was not ingested: {outcome.status.value}"
            )
        sources.append(mapping.source)
        outcomes.append(outcome)

    analytics = HistoricalPerformanceAnalytics(repository.all(), sources=sources)
    disciplines = _discipline_summaries(repository.all(), analytics, sources)
    return PrivateHistoryRunReport(
        imported_items=len(imports),
        canonical_results=len(repository.all()),
        duplicate_items=sum(
            outcome.status == IngestOutcomeStatus.DUPLICATE for outcome in outcomes
        ),
        conflict_items=sum(
            outcome.status == IngestOutcomeStatus.CONFLICT for outcome in outcomes
        ),
        disciplines=disciplines,
    )


def _discipline_summaries(
    results: tuple[HistoricalResult, ...],
    analytics: HistoricalPerformanceAnalytics,
    sources: list[object],
) -> list[DisciplineHistorySummary]:
    by_discipline: dict[tuple[int, str, str], list[HistoricalResult]] = defaultdict(list)
    for result in results:
        by_discipline[
            (result.distance_m, result.stroke.value, result.pool_length.value)
        ].append(result)

    summaries: list[DisciplineHistorySummary] = []
    source_by_id = {source.id: source for source in sources}
    for key in sorted(by_discipline):
        discipline_results = sorted(by_discipline[key], key=_chronology_key)
        latest = discipline_results[-1]
        progression = analytics.result_progression(latest)
        personal_best = analytics.personal_best(latest)
        trend = analytics.trend(latest)
        delta = analytics.delta_to_previous(latest)
        latest_source = source_by_id.get(latest.source_id)

        result_explanation = generate_explanation(
            ExplanationContext(
                explanation_type=ExplanationType.RESULT_SUMMARY,
                athlete_id=latest.athlete_id,
                result_id=latest.id,
                competition_id=latest.competition_id,
                event_id=latest.event_id,
                historical_result=latest,
                source_provenance=[latest_source] if latest_source is not None else [],
                verification_status=latest.verification_status,
                language=LanguageCode.RU,
            ),
            LanguageCode.RU,
        )
        progression_summary = None
        if delta.available:
            progression_explanation = generate_explanation(
                ExplanationContext(
                    explanation_type=ExplanationType.PROGRESSION_SUMMARY,
                    athlete_id=latest.athlete_id,
                    result_id=latest.id,
                    competition_id=latest.competition_id,
                    event_id=latest.event_id,
                    historical_result=latest,
                    analytics=AnalyticsExplanationContext(
                        progression=list(progression),
                        delta_to_previous=delta,
                        trend=trend,
                    ),
                    source_provenance=(
                        [latest_source] if latest_source is not None else []
                    ),
                    verification_status=latest.verification_status,
                    language=LanguageCode.RU,
                ),
                LanguageCode.RU,
            )
            progression_summary = progression_explanation.summary

        summaries.append(
            DisciplineHistorySummary(
                discipline=_discipline_label(latest),
                canonical_results=len(discipline_results),
                analytics_points=len(progression),
                latest_result_id=str(latest.id),
                latest_date=latest.swim_date.isoformat(),
                latest_time=latest.official_time_raw or "нет времени",
                verification_status=latest.verification_status.value,
                personal_best_time=(
                    None
                    if personal_best is None
                    else _time_for_result(results, personal_best.result_id)
                ),
                trend_status=trend.status.value,
                result_summary=result_explanation.summary
                or "Русское объяснение результата недоступно.",
                progression_summary=progression_summary,
            )
        )
    return summaries


def _chronology_key(result: HistoricalResult) -> tuple[object, ...]:
    return (result.swim_date, result.created_at, str(result.id))


def _discipline_label(result: HistoricalResult) -> str:
    return f"{result.distance_m} м {result.stroke.value}, {result.pool_length.value}"


def _time_for_result(results: tuple[HistoricalResult, ...], result_id: object) -> str | None:
    for result in results:
        if result.id == result_id:
            return result.official_time_raw
    return None


def render_history_report(report: PrivateHistoryRunReport) -> str:
    """Render a concise Russian report without private source payload fields."""

    lines = [
        "Локальный импорт истории выполнен.",
        f"Элементов во входе: {report.imported_items}",
        f"Канонических результатов: {report.canonical_results}",
        f"Дубликатов: {report.duplicate_items}",
        f"Конфликтов: {report.conflict_items}",
        "Дисциплины:",
    ]
    for discipline in report.disciplines:
        lines.extend(
            [
                f"- {discipline.discipline}",
                f"  Канонических результатов: {discipline.canonical_results}",
                f"  Точек аналитики: {discipline.analytics_points}",
                f"  Последний результат: {discipline.latest_time} "
                f"({discipline.latest_date})",
                f"  Статус проверки: {discipline.verification_status}",
                f"  PB: {discipline.personal_best_time or 'недоступно'}",
                f"  Тренд: {discipline.trend_status}",
                f"  Итог: {discipline.result_summary}",
            ]
        )
        if discipline.progression_summary is not None:
            lines.append(f"  Динамика: {discipline.progression_summary}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run already-structured private history JSON from data/private/ "
            "through the local Athlete Context pipeline."
        )
    )
    parser.add_argument("path", help="Path to a JSON file inside data/private/")
    args = parser.parse_args()
    try:
        print(render_history_report(run_private_history(args.path)))
    except PrivateHistoryRunError as error:
        print(f"Ошибка: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
