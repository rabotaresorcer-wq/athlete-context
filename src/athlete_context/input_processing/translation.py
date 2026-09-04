"""Translation boundary and deterministic local stub implementation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from athlete_context.input_processing.models import LanguageCode

TranslationKey = tuple[str, LanguageCode, LanguageCode]


class TranslationUnavailableError(LookupError):
    """Raised when a translator has no deterministic translation for an input."""


class Translator(Protocol):
    """Boundary implemented by future translation adapters."""

    def translate(
        self,
        text: str,
        *,
        source_language: LanguageCode,
        target_language: LanguageCode,
    ) -> str:
        """Return derivative translated text without changing the source text."""


class DeterministicTranslator:
    """Mapping-backed translator for deterministic tests and local workflows."""

    def __init__(self, translations: Mapping[TranslationKey, str]) -> None:
        self._translations = dict(translations)

    def translate(
        self,
        text: str,
        *,
        source_language: LanguageCode,
        target_language: LanguageCode,
    ) -> str:
        key = (text, source_language, target_language)
        try:
            return self._translations[key]
        except KeyError as error:
            raise TranslationUnavailableError(
                "no deterministic translation is available"
            ) from error
