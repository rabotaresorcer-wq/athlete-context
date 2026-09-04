"""Deterministic tests for the Layer 4 input-processing foundation."""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from athlete_context.input_processing import (
    ContentType,
    DeterministicTranslator,
    InputProcessingService,
    LanguageCode,
    RawInput,
    TranslationStatus,
    detect_language,
)

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
SOURCE_ID = UUID("61000000-0000-0000-0000-000000000001")
INPUT_ID = UUID("61000000-0000-0000-0000-000000000002")
RU_TEXT = "Результат заплыва подтверждён"
TR_TEXT = "Yüzme sonucu doğrulandı"
EN_TEXT = "The swimming result is verified"


def make_raw_text(
    text: str,
    *,
    content_type: ContentType = ContentType.MESSAGE,
    original_language: LanguageCode | None = None,
) -> RawInput:
    return RawInput(
        id=INPUT_ID,
        source_id=SOURCE_ID,
        content_type=content_type,
        raw_text=text,
        original_language=original_language,
        captured_at=NOW,
    )


def test_russian_text_detection() -> None:
    assert detect_language(RU_TEXT) == LanguageCode.RU


def test_turkish_text_detection() -> None:
    assert detect_language(TR_TEXT) == LanguageCode.TR


def test_english_text_detection() -> None:
    assert detect_language(EN_TEXT) == LanguageCode.EN


@pytest.mark.parametrize("text", ["", "42!", "泳ぐ結果"])
def test_unknown_language(text: str) -> None:
    assert detect_language(text) == LanguageCode.UNKNOWN


def test_russian_text_does_not_require_translation() -> None:
    normalized = InputProcessingService().process_input(make_raw_text(RU_TEXT))

    assert normalized.original_language == LanguageCode.RU
    assert normalized.original_text == RU_TEXT
    assert normalized.translated_text is None
    assert normalized.target_language == LanguageCode.RU
    assert normalized.translation_status == TranslationStatus.NOT_REQUIRED


def test_turkish_text_translates_to_russian_with_stub() -> None:
    translated = "Результат плавания подтверждён"
    translator = DeterministicTranslator(
        {(TR_TEXT, LanguageCode.TR, LanguageCode.RU): translated}
    )

    normalized = InputProcessingService(translator).process_input(
        make_raw_text(TR_TEXT)
    )

    assert normalized.original_language == LanguageCode.TR
    assert normalized.original_text == TR_TEXT
    assert normalized.translated_text == translated
    assert normalized.translation_status == TranslationStatus.TRANSLATED


def test_english_text_translates_to_russian_with_stub() -> None:
    translated = "Результат по плаванию подтверждён"
    translator = DeterministicTranslator(
        {(EN_TEXT, LanguageCode.EN, LanguageCode.RU): translated}
    )

    normalized = InputProcessingService(translator).process_input(
        make_raw_text(EN_TEXT)
    )

    assert normalized.original_language == LanguageCode.EN
    assert normalized.translated_text == translated
    assert normalized.target_language == LanguageCode.RU
    assert normalized.translation_status == TranslationStatus.TRANSLATED


def test_translation_is_unavailable_without_translator() -> None:
    normalized = InputProcessingService().process_input(make_raw_text(EN_TEXT))

    assert normalized.original_text == EN_TEXT
    assert normalized.translated_text is None
    assert normalized.translation_status == TranslationStatus.UNAVAILABLE


def test_translation_is_unavailable_when_stub_has_no_mapping() -> None:
    normalized = InputProcessingService(DeterministicTranslator({})).process_input(
        make_raw_text(EN_TEXT)
    )

    assert normalized.original_text == EN_TEXT
    assert normalized.translated_text is None
    assert normalized.translation_status == TranslationStatus.UNAVAILABLE


def test_translation_failure_preserves_original() -> None:
    class FailingTranslator:
        def translate(
            self,
            text: str,
            *,
            source_language: LanguageCode,
            target_language: LanguageCode,
        ) -> str:
            raise RuntimeError("synthetic translator failure")

    raw_input = make_raw_text(EN_TEXT)
    normalized = InputProcessingService(FailingTranslator()).process_input(raw_input)

    assert raw_input.raw_text == EN_TEXT
    assert normalized.original_text == EN_TEXT
    assert normalized.translated_text is None
    assert normalized.translation_status == TranslationStatus.FAILED


def test_document_text_input() -> None:
    normalized = InputProcessingService().process_input(
        make_raw_text(EN_TEXT, content_type=ContentType.DOCUMENT_TEXT)
    )

    assert normalized.content_type == ContentType.DOCUMENT_TEXT
    assert normalized.original_text == EN_TEXT


def test_message_input() -> None:
    normalized = InputProcessingService().process_input(make_raw_text(RU_TEXT))

    assert normalized.content_type == ContentType.MESSAGE
    assert normalized.source_id == SOURCE_ID
    assert normalized.input_id == INPUT_ID
    assert normalized.captured_at == NOW


def test_structured_data_is_identified_and_preserved() -> None:
    payload = {
        "result": {"time": "1:02.34", "official": True},
        "splits": ["30.10", "1:02.34"],
    }
    raw_input = RawInput(
        id=INPUT_ID,
        source_id=SOURCE_ID,
        content_type=ContentType.UNKNOWN,
        structured_data=payload,
        captured_at=NOW,
    )

    normalized = InputProcessingService().process_input(raw_input)

    assert normalized.content_type == ContentType.STRUCTURED_DATA
    assert normalized.structured_data == payload
    assert normalized.original_text is None
    assert normalized.original_language == LanguageCode.UNKNOWN
    assert normalized.translation_status == TranslationStatus.NOT_REQUIRED
    assert normalized.target_language is None


def test_explicit_valid_source_language_is_preserved() -> None:
    raw_input = make_raw_text(
        EN_TEXT,
        original_language=LanguageCode.TR,
    )

    normalized = InputProcessingService().process_input(raw_input)

    assert normalized.original_language == LanguageCode.TR


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"raw_text": "   "},
        {"content_type": ContentType.MESSAGE, "structured_data": {"key": "value"}},
        {"content_type": ContentType.STRUCTURED_DATA, "raw_text": EN_TEXT},
    ],
)
def test_empty_or_invalid_input_is_rejected(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RawInput(source_id=SOURCE_ID, captured_at=NOW, **values)


def test_original_text_is_never_overwritten() -> None:
    translated = "Производный перевод"
    source_text = f"  {EN_TEXT}\n"
    raw_input = make_raw_text(source_text)
    translator = DeterministicTranslator(
        {(source_text, LanguageCode.EN, LanguageCode.RU): translated}
    )

    normalized = InputProcessingService(translator).process_input(raw_input)

    assert raw_input.raw_text == source_text
    assert normalized.original_text == source_text
    assert normalized.translated_text == translated
    assert normalized.original_text != normalized.translated_text
