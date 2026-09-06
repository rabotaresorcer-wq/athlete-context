"""Synthetic tests for the local private analytics agent."""

from __future__ import annotations

import json
from pathlib import Path
from runpy import run_path

import pytest

AGENT = run_path(
    str(Path(__file__).parents[1] / "examples" / "athlete_analytics_agent.py")
)

AthleteAnalyticsAgentError = AGENT["AthleteAnalyticsAgentError"]
resolve_private_report_path = AGENT["resolve_private_report_path"]
run_athlete_analytics_agent = AGENT["run_athlete_analytics_agent"]


def result_payload(number: int, **updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": f"a4000000-0000-0000-0000-{number:012d}",
        "original_source": f"Synthetic analytics agent source {number}",
        "original_language": "tr",
        "captured_at": f"2026-09-06T12:{number:02d}:00+00:00",
        "source_type": "OFFICIAL_FEDERATION_RESULT",
        "source_reference": f"synthetic-agent-history:{number}",
        "source_url": f"https://example.test/synthetic-agent-history/{number}",
        "athlete_id": "a1000000-0000-0000-0000-000000000001",
        "athlete_reference": "synthetic-athlete:agent",
        "competition_id": f"a2000000-0000-0000-0000-{number:012d}",
        "competition_reference": f"synthetic-competition:agent-{number}",
        "event_id": "a3000000-0000-0000-0000-000000000001",
        "event_reference": "synthetic-event:100-free-lcm",
        "swim_date": f"2026-08-{number:02d}",
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


def make_private_history(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository_root = tmp_path / "repo"
    private_dir = repository_root / "data" / "private"
    private_dir.mkdir(parents=True)
    history_path = private_dir / "history.json"
    history_path.write_text(
        json.dumps(
            {
                "results": [
                    result_payload(1, official_time_raw="1:01.20"),
                    result_payload(2, official_time_raw="1:00.40"),
                    result_payload(3, official_time_raw="59.90"),
                ]
            }
        ),
        encoding="utf-8",
    )
    return repository_root, private_dir, history_path


def test_report_path_guard_rejects_outputs_outside_private_data(tmp_path: Path) -> None:
    repository_root, private_dir, _ = make_private_history(tmp_path)

    with pytest.raises(AthleteAnalyticsAgentError, match="inside data/private"):
        resolve_private_report_path(
            repository_root / "reports" / "latest.md",
            private_data_dir=private_dir,
            repository_root=repository_root,
        )


def test_agent_writes_markdown_report_inside_private_data(tmp_path: Path) -> None:
    repository_root, private_dir, history_path = make_private_history(tmp_path)
    report_path = private_dir / "reports" / "latest-analytics.md"

    run = run_athlete_analytics_agent(
        history_path,
        report_path,
        private_data_dir=private_dir,
        repository_root=repository_root,
    )

    assert run.report_path == report_path
    assert report_path.read_text(encoding="utf-8") == run.report_text
    assert run.report_text.startswith("# Athlete Context Analytics Report")
    assert "Локальный импорт истории выполнен." in run.report_text
    assert "PB: 59.90" in run.report_text
    assert "Synthetic analytics agent source" not in run.report_text
    assert "synthetic-agent-history" not in run.report_text
