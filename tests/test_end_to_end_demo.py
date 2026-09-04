"""Genuine synthetic integration coverage across Athlete Context Layers 1–7."""

from pathlib import Path
from runpy import run_path


DEMO = run_path(
    str(Path(__file__).parents[1] / "examples" / "demo_end_to_end.py")
)
COMPETITION_ID = DEMO["COMPETITION_ID"]
EVENT_ID = DEMO["EVENT_ID"]
RUSSIAN_TRANSLATION = DEMO["RUSSIAN_TRANSLATION"]
TURKISH_MESSAGE = DEMO["TURKISH_MESSAGE"]
run_demo = DEMO["run_demo"]


def test_synthetic_end_to_end_demo() -> None:
    demo = run_demo()

    language_flow = demo["language_flow"]
    assert language_flow["original_turkish"] == TURKISH_MESSAGE
    assert language_flow["detected_language"] == "TR"
    assert language_flow["russian_translation"] == RUSSIAN_TRANSLATION
    assert language_flow["original_preserved"] is True

    linking = demo["linking"]
    assert linking["status"] == "LINKED"
    assert linking["verification_status"] == "UNVERIFIED"
    assert linking["competition_id"] == str(COMPETITION_ID)
    assert linking["event_id"] == str(EVENT_ID)

    official_result = demo["official_result"]
    assert official_result["ingest_status"] == "CREATED"
    assert official_result["time"] == "29.60"
    assert official_result["pool_length"] == "LCM_50M"
    assert official_result["verification_status"] == "VERIFIED"

    analytics = demo["analytics"]
    assert analytics["previous_time"] == "29.90"
    assert analytics["delta_centiseconds"] == -30
    assert analytics["new_personal_best"] is True
    assert analytics["personal_best_result_id"] == official_result["result_id"]
    assert analytics["trend"] == "IMPROVING"
    assert analytics["trend_sample_size"] == 3
    assert analytics["consistency_status"] == "AVAILABLE"
    assert analytics["scm_control_time"] == "28.00"
    assert analytics["scm_control_excluded"] is True
    assert len(analytics["progression_result_ids"]) == 3

    lifecycle = demo["competition_lifecycle"]
    assert lifecycle["explicitly_approved"] is True
    assert lifecycle["monitoring_competition_id"] == str(COMPETITION_ID)
    assert lifecycle["update_type"] == "RESULT"
    assert lifecycle["lifecycle_status"] == "CLOSED"
    assert lifecycle["live_federation_access"] is False

    provenance = demo["provenance"]
    assert linking["source_id"] == provenance["message_source_id"]
    assert official_result["source_id"] == provenance["official_result_source_id"]
    assert provenance["official_result_source_id"] in (
        provenance["explanation_source_ids"]
    )

    explanation = demo["final_explanation"]
    assert explanation["language"] == "RU"
    assert explanation["summary"] == (
        "По сравнению с предыдущим сопоставимым результатом это быстрее "
        "на 0.30 секунды."
    )
    assert "подтверждены" in explanation["verification_note"]

    assert language_flow["russian_translation"] != language_flow["original_turkish"]
    assert linking["verification_status"] != official_result["verification_status"]
