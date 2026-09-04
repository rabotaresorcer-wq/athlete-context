"""Orchestration for deterministic, source-preserving input normalization."""

from __future__ import annotations

from copy import deepcopy

from athlete_context.input_processing.language import detect_language
from athlete_context.input_processing.models import (
    ContentType,
    LanguageCode,
    NormalizedInput,
    RawInput,
    TranslationStatus,
)
from athlete_context.input_processing.translation import (
    TranslationUnavailableError,
    Translator,
)


class InputProcessingService:
    """Normalize available text or structured data without interpreting facts."""

    def __init__(self, translator: Translator | None = None) -> None:
        self._translator = translator

    def process_input(
        self,
        raw_input: RawInput,
        target_language: LanguageCode = LanguageCode.RU,
    ) -> NormalizedInput:
        if not isinstance(raw_input, RawInput):
            raise TypeError("raw_input must be a validated RawInput")
        if target_language == LanguageCode.UNKNOWN:
            raise ValueError("target_language must be known")

        content_type = self._identify_content_type(raw_input)
        language = self._identify_language(raw_input)
        translated_text: str | None = None
        translated_target: LanguageCode | None = None

        if raw_input.raw_text is None:
            status = TranslationStatus.NOT_REQUIRED
        elif language == target_language:
            status = TranslationStatus.NOT_REQUIRED
            translated_target = target_language
        elif language == LanguageCode.UNKNOWN or self._translator is None:
            status = TranslationStatus.UNAVAILABLE
            translated_target = target_language
        else:
            translated_target = target_language
            try:
                candidate = self._translator.translate(
                    raw_input.raw_text,
                    source_language=language,
                    target_language=target_language,
                )
                if not isinstance(candidate, str) or not candidate.strip():
                    raise ValueError("translator returned empty text")
                translated_text = candidate
                status = TranslationStatus.TRANSLATED
            except TranslationUnavailableError:
                status = TranslationStatus.UNAVAILABLE
            except Exception:
                status = TranslationStatus.FAILED

        return NormalizedInput(
            input_id=raw_input.id,
            source_id=raw_input.source_id,
            content_type=content_type,
            original_text=raw_input.raw_text,
            original_language=language,
            translated_text=translated_text,
            target_language=translated_target,
            structured_data=deepcopy(raw_input.structured_data),
            translation_status=status,
            captured_at=raw_input.captured_at,
        )

    @staticmethod
    def _identify_content_type(raw_input: RawInput) -> ContentType:
        if raw_input.content_type != ContentType.UNKNOWN:
            return raw_input.content_type
        if raw_input.structured_data is not None and raw_input.raw_text is None:
            return ContentType.STRUCTURED_DATA
        return ContentType.UNKNOWN

    @staticmethod
    def _identify_language(raw_input: RawInput) -> LanguageCode:
        if raw_input.original_language not in {None, LanguageCode.UNKNOWN}:
            return raw_input.original_language
        if raw_input.raw_text is None:
            return LanguageCode.UNKNOWN
        return detect_language(raw_input.raw_text)


def process_input(
    raw_input: RawInput,
    target_language: LanguageCode = LanguageCode.RU,
    *,
    translator: Translator | None = None,
) -> NormalizedInput:
    """Convenience wrapper around the Layer 4 orchestration service."""

    return InputProcessingService(translator).process_input(
        raw_input,
        target_language=target_language,
    )
