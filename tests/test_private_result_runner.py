"""Synthetic tests for the controlled local private-result runner."""

from __future__ import annotations

import json
from pathlib import Path
from runpy import run_path
from subprocess import run

import pytest

RUNNER = run_path(
    str(Path(__file__).parents[1] / "examples" / "run_private_result.py")
)
PrivateResultRunError = RUNNER["PrivateResultRunError"]
load_private_result_import = RUNNER["load_private_result_import"]
render_summary = RUNNER["render_summary"]
resolve_private_result_path = RUNNER["resolve_private_result_path"]
run_private_result = RUNNER["run_private_result"]


def synthetic_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": "d4000000-0000-0000-0000-000000000001",
        "original_source": "Synthetic private official result source",
        "original_language": "tr",
        "captured_at": "2026-09-06T12:00:00+00:00",
        "source_type": "OFFICIAL_FEDERATION_RESULT",
        "source_reference": "synthetic-private-result:1",
        "source_url": "https://example.test/synthetic-private-result/1",
        "athlete_id": "d1000000-0000-0000-0000-000000000001",
        "athlete_reference": "synthetic-athlete:private-run",
        "competition_id": "d2000000-0000-0000-0000-000000000001",
        "competition_reference": "synthetic-competition:private-run",
        "event_id": "d3000000-0000-0000-0000-000000000001",
        "event_reference": "synthetic-event:private-run",
        "swim_date": "2026-09-01",
        "distance_m": 100,
        "stroke": "FREESTYLE",
        "pool_length": "LCM_50M",
        "official_time_raw": "59.50",
        "round": "FINAL",
        "aqua_points": 612,
        "standard_status": "UNKNOWN",
        "result_status": "OFFICIAL",
        "verification_status": "VERIFIED",
    }
    payload.update(updates)
    return payload


def make_private_file(
    tmp_path: Path,
    payload: dict[str, object] | str,
) -> tuple[Path, Path, Path]:
    repository_root = tmp_path / "repo"
    private_dir = repository_root / "data" / "private"
    private_dir.mkdir(parents=True)
    private_file = private_dir / "result.json"
    if isinstance(payload, str):
        private_file.write_text(payload, encoding="utf-8")
    else:
        private_file.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
    return repository_root, private_dir, private_file


def test_private_path_guard_rejects_paths_outside_data_private(
    tmp_path: Path,
) -> None:
    repository_root, private_dir, _ = make_private_file(
        tmp_path,
        synthetic_payload(),
    )
    outside = repository_root / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(PrivateResultRunError, match="inside data/private"):
        resolve_private_result_path(
            outside,
            private_data_dir=private_dir,
            repository_root=repository_root,
        )


def test_malformed_json_fails_safely(tmp_path: Path) -> None:
    repository_root, private_dir, private_file = make_private_file(
        tmp_path,
        "{not valid json",
    )

    with pytest.raises(PrivateResultRunError, match="not valid JSON"):
        load_private_result_import(
            private_file,
            private_data_dir=private_dir,
            repository_root=repository_root,
        )


def test_valid_synthetic_private_input_reaches_existing_pipeline(
    tmp_path: Path,
) -> None:
    repository_root, private_dir, private_file = make_private_file(
        tmp_path,
        synthetic_payload(),
    )

    result = run_private_result(
        private_file,
        private_data_dir=private_dir,
        repository_root=repository_root,
    )
    output = render_summary(result)

    assert result.ingest_status == "CREATED"
    assert result.analytics_points == 1
    assert result.summary.startswith("Официальный результат")
    assert "synthetic-private-result" not in output
    assert "Synthetic private official result source" not in output


def test_verification_status_is_preserved_in_controlled_run(
    tmp_path: Path,
) -> None:
    repository_root, private_dir, private_file = make_private_file(
        tmp_path,
        synthetic_payload(verification_status="UNVERIFIED"),
    )

    result = run_private_result(
        private_file,
        private_data_dir=private_dir,
        repository_root=repository_root,
    )

    assert result.verification_status == "UNVERIFIED"
    assert "не проверена" in result.verification_note


def test_pool_length_is_preserved_in_controlled_run(tmp_path: Path) -> None:
    repository_root, private_dir, private_file = make_private_file(
        tmp_path,
        synthetic_payload(pool_length="SCM_25M", official_time_raw="57.80"),
    )

    result = run_private_result(
        private_file,
        private_data_dir=private_dir,
        repository_root=repository_root,
    )

    assert result.pool_length == "SCM_25M"
    assert "25-метровом бассейне" in result.summary


def test_no_committed_private_file_is_required() -> None:
    tracked = run(
        ["git", "ls-files", "data/private"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert tracked.stdout == ""
