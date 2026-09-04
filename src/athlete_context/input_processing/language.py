"""Small deterministic language heuristics for Layer 4 text input."""

from __future__ import annotations

import re

from athlete_context.input_processing.models import LanguageCode

_CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")
_LATIN_PATTERN = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]")
_TURKISH_SPECIFIC_PATTERN = re.compile(r"[ÇĞİÖŞÜçğıöşü]")
_WORD_PATTERN = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]+")
_TURKISH_MARKERS = {
    "bir",
    "bu",
    "değil",
    "için",
    "ile",
    "merhaba",
    "sonuç",
    "ve",
    "yüzme",
}


def detect_language(text: str) -> LanguageCode:
    """Classify clear Russian, Turkish, or English text using fixed heuristics."""

    if not isinstance(text, str) or not text.strip():
        return LanguageCode.UNKNOWN

    cyrillic_count = len(_CYRILLIC_PATTERN.findall(text))
    latin_count = len(_LATIN_PATTERN.findall(text))
    letter_count = sum(character.isalpha() for character in text)
    if letter_count < 3:
        return LanguageCode.UNKNOWN

    if cyrillic_count / letter_count >= 0.6:
        return LanguageCode.RU

    if latin_count / letter_count >= 0.8:
        if _TURKISH_SPECIFIC_PATTERN.search(text):
            return LanguageCode.TR
        words = {word.casefold() for word in _WORD_PATTERN.findall(text)}
        if len(words & _TURKISH_MARKERS) >= 2:
            return LanguageCode.TR
        return LanguageCode.EN

    return LanguageCode.UNKNOWN
