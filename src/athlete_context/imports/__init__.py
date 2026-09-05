"""Import boundaries for already-structured external result data."""

from athlete_context.imports.official_results import (
    OfficialResultImport,
    OfficialResultImportMapping,
    OfficialResultImportService,
)

__all__ = [
    "OfficialResultImport",
    "OfficialResultImportMapping",
    "OfficialResultImportService",
]
