"""Synthetic tests for the controlled private history runner."""

from __future__ import annotations

import json
from pathlib import Path
from runpy import run_path
from subprocess import run

import pytest

RUNNER = run_path(
    str(Path(__file__).parents[1] / "examples" / "run_private_history.py")
)
PrivateHistoryRunError = RUNNER["PrivateHistoryRunError"]
load_private_history_imports = RUNNER["load_private_history_imports"]
render_history_report = RUNNER["render_history_report"]
resolve_private_history_path = RUNNER["resolve_private_history_path"]
run_private_history = RUNNER["run_private_history"]


def result_payload(number: int, **updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": f"f4000000-0000-0000-0000-{number:012d}",
        "original_source": f"Synthetic official history source {number}",
        "original_language": "tr",
        "captured_at": f"2026-09-06T12:{number:02d}:00+00:00",
        "source_type": "OFFICIAL_FEDERATION_RESULT",
        "source_reference": f"synthetic-history-result:{number}",
        "source_url": f"https://example.test/synthetic-history/{number}",
        "athlete_id": "f1000000-0000-0000-0000-000000000001",
        "athlete_reference": "synthetic-athlete:history",
        "competition_id": f"f2000000-0000-0000-0000-{number:012d}",
        "competition_reference": f"synthetic-competition:history-{number}",
        "event_id": "f3000000-0000-0000-0000-000000000001",
        "event_reference": "synthetic-event:100-free-lcm",
        "swim_date": f"2026-07-{number:02d}",
        "distance_m": 100,
        "stroke": "FREESTYLE",
        "pool_length": "LCM_50M",
        "official_time_raw": "1:00.40",
        "round": "FINAL",
        "aqua_points": 604,
        "standard_status": "UNKNOWN",
        "result_status": "OFFICIAL",
        "verification_status": "VERIFIED",
    }
    payload.update(updates)
    return payload


def make_private_history_file(
    tmp_path: Path,
    payload: dict[str, object] | str,
) -> tuple[Path, Path, Path]:
    repository_root = tmp_path / "repo"
    private_dir = repository_root / "data" / "private"
    private_dir.mkdir(parents=True)
    private_file = private_dir / "history.json"
    if isinstance(payload, str):
        private_file.write_text(payload, encoding="utf-8")
    else:
        private_file.write_text(json.dumps(payload), encoding="utf-8")
    return repository_root, private_dir, private_file


def run_history_with_payload(
    tmp_path: Path,
    payload: dict[str, object] | str,
):
    repository_root, private_dir, private_file = make_private_history_file(
        tmp_path,
        payload,
    )
    return run_private_history(
        private_file,
        private_data_dir=private_dir,
        repository_root=repository_root,
    )


def test_private_history_path_guard_rejects_outside_paths(tmp_path: Path) -> None:
    repository_root, private_dir, _ = make_private_history_file(
        tmp_path,
        {"results": [result_payload(1)]},
    )
    outside = repository_root / "history.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(PrivateHistoryRunError, match="inside data/private"):
        resolve_private_history_path(
            outside,
            private_data_dir=private_dir,
            repository_root=repository_root,
        )


def test_malformed_history_json_fails_safely(tmp_path: Path) -> None:
    repository_root, private_dir, private_file = make_private_history_file(
        tmp_path,
        "{not valid json",
    )

    with pytest.raises(PrivateHistoryRunError, match="not valid JSON"):
        load_private_history_imports(
            private_file,
            private_data_dir=private_dir,
            repository_root=repository_root,
        )


def test_private_history_requires_non_empty_results(tmp_path: Path) -> None:
    repository_root, private_dir, private_file = make_private_history_file(
        tmp_path,
        {"results": []},
    )

    with pytest.raises(PrivateHistoryRunError, match="non-empty results"):
        load_private_history_imports(
            private_file,
            private_data_dir=private_dir,
            repository_root=repository_root,
        )


def test_multiple_results_use_one_repository_and_existing_analytics(
    tmp_path: Path,
) -> None:
    report = run_history_with_payload(
        tmp_path,
        {
            "results": [
                result_payload(1, swim_date="2026-07-01", official_time_raw="1:01.20"),
                result_payload(2, swim_date="2026-07-15", official_time_raw="1:00.40"),
                result_payload(3, swim_date="2026-08-01", official_time_raw="59.90"),
            ]
        },
    )

    assert report.imported_items == 3
    assert report.canonical_results == 3
    assert len(report.disciplines) == 1
    discipline = report.disciplines[0]
    assert discipline.analytics_points == 3
    assert discipline.personal_best_time == "59.90"
    assert discipline.trend_status == "IMPROVING"
    assert discipline.progression_summary is not None
    assert "быстрее" in discipline.progression_summary


def test_history_report_groups_scm_and_lcm_separately(tmp_path: Path) -> None:
    report = run_history_with_payload(
        tmp_path,
        {
            "results": [
                result_payload(4, pool_length="LCM_50M", official_time_raw="59.90"),
                result_payload(
                    5,
                    pool_length="SCM_25M",
                    official_time_raw="57.80",
                    event_reference="synthetic-event:100-free-scm",
                ),
            ]
        },
    )

    disciplines = {item.discipline for item in report.disciplines}
    assert disciplines == {
        "100 м FREESTYLE, LCM_50M",
        "100 м FREESTYLE, SCM_25M",
    }


def test_history_runner_preserves_unverified_status(tmp_path: Path) -> None:
    report = run_history_with_payload(
        tmp_path,
        {
            "results": [
                result_payload(6, verification_status="UNVERIFIED"),
            ]
        },
    )

    assert report.disciplines[0].verification_status == "UNVERIFIED"
    assert "Непроверенная запись" in report.disciplines[0].result_summary


def test_rendered_history_report_is_russian_and_omits_source_payload(
    tmp_path: Path,
) -> None:
    report = run_history_with_payload(
        tmp_path,
        {
            "results": [
                result_payload(7, official_time_raw="1:00.40"),
                result_payload(8, official_time_raw="59.90"),
            ]
        },
    )

    output = render_history_report(report)

    assert output.startswith("Локальный импорт истории выполнен.")
    assert "Дисциплины:" in output
    assert "Synthetic official history source" not in output
    assert "synthetic-history-result" not in output


def test_no_committed_private_history_file_is_required() -> None:
    tracked = run(
        ["git", "ls-files", "data/private"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert tracked.stdout == ""
