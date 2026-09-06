"""Local private analytics agent for Athlete Context history files."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))

from run_private_history import (
    PRIVATE_DATA_DIR,
    REPOSITORY_ROOT,
    PrivateHistoryRunError,
    render_history_report,
    run_private_history,
)

DEFAULT_HISTORY_PATH = PRIVATE_DATA_DIR / "history.json"
DEFAULT_REPORT_PATH = PRIVATE_DATA_DIR / "reports" / "latest-analytics.md"


class AthleteAnalyticsAgentError(RuntimeError):
    """Safe user-facing error for local analytics-agent runs."""


@dataclass(frozen=True)
class AthleteAnalyticsAgentRun:
    """Result metadata for one local analytics-agent run."""

    input_path: Path
    report_path: Path
    report_text: str


def resolve_private_report_path(
    supplied_path: str | Path,
    *,
    private_data_dir: Path = PRIVATE_DATA_DIR,
    repository_root: Path = REPOSITORY_ROOT,
) -> Path:
    """Return a report path only when it stays inside data/private."""

    path = Path(supplied_path).expanduser()
    if not path.is_absolute():
        path = repository_root / path
    resolved = path.resolve(strict=False)
    private_root = private_data_dir.resolve(strict=False)
    if not resolved.is_relative_to(private_root):
        raise AthleteAnalyticsAgentError("analytics report path must be inside data/private/")
    return resolved


def build_markdown_report(rendered_summary: str) -> str:
    """Wrap the existing Russian analytics summary as a reusable local report."""

    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    return "\n".join(
        [
            "# Athlete Context Analytics Report",
            "",
            f"Generated at: {generated_at}",
            "",
            "## Summary",
            "",
            rendered_summary,
            "",
            "## Boundary",
            "",
            "- Отчёт построен только по локальному structured JSON из `data/private/`.",
            "- Реальные исходные payload, source dumps и приватные сообщения не печатаются.",
            "- Аналитика не является тренерской рекомендацией или медицинским советом.",
            "",
        ]
    )


def run_athlete_analytics_agent(
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    *,
    private_data_dir: Path = PRIVATE_DATA_DIR,
    repository_root: Path = REPOSITORY_ROOT,
) -> AthleteAnalyticsAgentRun:
    """Run private history analytics and write a local markdown report."""

    resolved_report_path = resolve_private_report_path(
        report_path,
        private_data_dir=private_data_dir,
        repository_root=repository_root,
    )
    try:
        report = run_private_history(
            history_path,
            private_data_dir=private_data_dir,
            repository_root=repository_root,
        )
    except PrivateHistoryRunError as error:
        raise AthleteAnalyticsAgentError(str(error)) from error

    report_text = build_markdown_report(render_history_report(report))
    try:
        resolved_report_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_report_path.write_text(report_text, encoding="utf-8")
    except OSError as error:
        raise AthleteAnalyticsAgentError("analytics report could not be written") from error

    input_path = Path(history_path)
    if not input_path.is_absolute():
        input_path = repository_root / input_path
    return AthleteAnalyticsAgentRun(
        input_path=input_path.resolve(strict=False),
        report_path=resolved_report_path,
        report_text=report_text,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local Athlete Context analytics agent on a private "
            "history file from data/private/."
        )
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_HISTORY_PATH.relative_to(REPOSITORY_ROOT)),
        help="Path to private history JSON inside data/private/.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_REPORT_PATH.relative_to(REPOSITORY_ROOT)),
        help="Path for the generated report inside data/private/.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Also print the generated report text.",
    )
    args = parser.parse_args()

    try:
        run = run_athlete_analytics_agent(args.input, args.output)
    except AthleteAnalyticsAgentError as error:
        print(f"Ошибка: {error}")
        return 1

    print(f"Аналитический отчёт готов: {run.report_path}")
    if args.print:
        print()
        print(run.report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
