"""Run one private structured result through the existing Athlete Context pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from athlete_context.analytics import HistoricalPerformanceAnalytics
from athlete_context.explanation import (
    ExplanationContext,
    ExplanationType,
    generate_explanation,
)
from athlete_context.imports import OfficialResultImport, OfficialResultImportService
from athlete_context.input_processing import LanguageCode
from athlete_context.services import (
    HistoricalResultIngestService,
    InMemoryHistoricalResultRepository,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DATA_DIR = REPOSITORY_ROOT / "data" / "private"


class PrivateResultRunError(RuntimeError):
    """Safe user-facing error for controlled private result runs."""


@dataclass(frozen=True)
class PrivateResultRunSummary:
    """Minimal non-payload output from one controlled private result run."""

    ingest_status: str
    result_id: str
    verification_status: str
    pool_length: str
    analytics_points: int
    summary: str
    verification_note: str


def resolve_private_result_path(
    supplied_path: str | Path,
    *,
    private_data_dir: Path = PRIVATE_DATA_DIR,
    repository_root: Path = REPOSITORY_ROOT,
) -> Path:
    """Return an existing file path only when it is inside data/private."""

    path = Path(supplied_path).expanduser()
    if not path.is_absolute():
        path = repository_root / path
    resolved = path.resolve(strict=False)
    private_root = private_data_dir.resolve(strict=False)
    if not resolved.is_relative_to(private_root):
        raise PrivateResultRunError("private result path must be inside data/private/")
    if not resolved.is_file():
        raise PrivateResultRunError("private result file does not exist")
    return resolved


def load_private_result_import(
    path: str | Path,
    *,
    private_data_dir: Path = PRIVATE_DATA_DIR,
    repository_root: Path = REPOSITORY_ROOT,
) -> OfficialResultImport:
    """Load and validate one private JSON result without printing its payload."""

    private_path = resolve_private_result_path(
        path,
        private_data_dir=private_data_dir,
        repository_root=repository_root,
    )
    try:
        raw: Any = json.loads(private_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PrivateResultRunError("private result file is not valid JSON") from error
    except OSError as error:
        raise PrivateResultRunError("private result file could not be read") from error
    if not isinstance(raw, dict):
        raise PrivateResultRunError("private result JSON must be an object")
    try:
        return OfficialResultImport.model_validate(raw)
    except ValidationError as error:
        raise PrivateResultRunError(
            "private result JSON failed OfficialResultImport validation"
        ) from error


def run_private_result(
    path: str | Path,
    *,
    private_data_dir: Path = PRIVATE_DATA_DIR,
    repository_root: Path = REPOSITORY_ROOT,
) -> PrivateResultRunSummary:
    """Execute the local-only import, ingestion, analytics and explanation flow."""

    result_import = load_private_result_import(
        path,
        private_data_dir=private_data_dir,
        repository_root=repository_root,
    )
    import_service = OfficialResultImportService()
    try:
        mapping = import_service.map_import(result_import)
    except ValueError as error:
        raise PrivateResultRunError(str(error)) from error

    repository = InMemoryHistoricalResultRepository()
    ingest_service = HistoricalResultIngestService(repository)
    outcome = import_service.import_result(result_import, ingest_service)
    if outcome.record is None:
        raise PrivateResultRunError(
            f"private result was not ingested: {outcome.status.value}"
        )

    analytics = HistoricalPerformanceAnalytics(
        repository.all(),
        sources=[mapping.source],
    )
    progression = analytics.result_progression(outcome.record)
    explanation = generate_explanation(
        ExplanationContext(
            explanation_type=ExplanationType.RESULT_SUMMARY,
            athlete_id=outcome.record.athlete_id,
            result_id=outcome.record.id,
            competition_id=outcome.record.competition_id,
            event_id=outcome.record.event_id,
            historical_result=outcome.record,
            source_provenance=[mapping.source],
            verification_status=result_import.verification_status,
            language=LanguageCode.RU,
        ),
        LanguageCode.RU,
    )
    if explanation.summary is None or explanation.verification_note is None:
        raise PrivateResultRunError("Russian explanation summary is unavailable")
    return PrivateResultRunSummary(
        ingest_status=outcome.status.value,
        result_id=str(outcome.record.id),
        verification_status=outcome.record.verification_status.value,
        pool_length=outcome.record.pool_length.value,
        analytics_points=len(progression),
        summary=explanation.summary,
        verification_note=explanation.verification_note,
    )

def render_summary(summary: PrivateResultRunSummary) -> str:
    """Render concise Russian CLI output without private source payload fields."""

    return "\n".join(
        [
            "Локальный импорт результата выполнен.",
            f"Статус ingest: {summary.ingest_status}",
            f"ID результата: {summary.result_id}",
            f"Статус проверки: {summary.verification_status}",
            f"Бассейн: {summary.pool_length}",
            f"Точек аналитики: {summary.analytics_points}",
            f"Итог: {summary.summary}",
            f"Проверка: {summary.verification_note}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one already-structured private result JSON from data/private/ "
            "through the local Athlete Context pipeline."
        )
    )
    parser.add_argument("path", help="Path to a JSON file inside data/private/")
    args = parser.parse_args()
    try:
        print(render_summary(run_private_result(args.path)))
    except PrivateResultRunError as error:
        print(f"Ошибка: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
