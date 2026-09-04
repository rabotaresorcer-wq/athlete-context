"""Deterministic Context Linking orchestration over normalized input."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from uuid import UUID

from athlete_context.context_linking.models import (
    ContextLinkResult,
    EntityType,
    LinkStatus,
    RecordType,
)
from athlete_context.context_linking.repository import InMemoryContextRepository
from athlete_context.domain import VerificationStatus
from athlete_context.input_processing import ContentType, NormalizedInput

_REQUIRED_ENTITIES: dict[RecordType, frozenset[EntityType]] = {
    RecordType.RESULT: frozenset(
        {EntityType.ATHLETE, EntityType.COMPETITION, EntityType.EVENT}
    ),
    RecordType.STANDARD: frozenset({EntityType.EVENT}),
    RecordType.PROFESSIONAL_FEEDBACK: frozenset({EntityType.ATHLETE}),
}


@dataclass
class _Resolution:
    entity_id: UUID | None = None
    matched: dict[str, UUID] = field(default_factory=dict)
    unresolved: dict[str, str] = field(default_factory=dict)
    conflict: bool = False


class ContextLinkingService:
    """Resolve only exact structured identifiers and repository references."""

    def link_context(
        self,
        normalized_input: NormalizedInput,
        context_repository: InMemoryContextRepository,
    ) -> ContextLinkResult:
        if not isinstance(normalized_input, NormalizedInput):
            raise TypeError("normalized_input must be a validated NormalizedInput")
        if not isinstance(context_repository, InMemoryContextRepository):
            raise TypeError(
                "context_repository must be an InMemoryContextRepository"
            )

        structured_data = normalized_input.structured_data or {}
        record_type = self._identify_record_type(normalized_input)
        resolutions = {
            entity_type: self._resolve_entity(
                entity_type,
                structured_data,
                context_repository,
            )
            for entity_type in EntityType
        }

        required = _REQUIRED_ENTITIES.get(record_type, frozenset())
        for entity_type in required:
            resolution = resolutions[entity_type]
            if resolution.entity_id is None and not resolution.conflict:
                key = f"{entity_type.value.casefold()}_id"
                resolution.unresolved.setdefault(
                    key,
                    f"missing explicit {entity_type.value.casefold()} reference",
                )

        relationship_conflict = self._event_competition_conflict(
            resolutions,
            context_repository,
        )
        matched = {
            key: entity_id
            for entity_type in EntityType
            for key, entity_id in resolutions[entity_type].matched.items()
        }
        unresolved = {
            key: reason
            for entity_type in EntityType
            for key, reason in resolutions[entity_type].unresolved.items()
        }
        if record_type == RecordType.UNKNOWN:
            unresolved["record_type"] = (
                "missing or unsupported explicit record type"
            )
        if relationship_conflict:
            unresolved["event_competition"] = (
                "event belongs to a different competition"
            )

        conflict = relationship_conflict or any(
            resolution.conflict for resolution in resolutions.values()
        )
        status = self._link_status(
            record_type=record_type,
            matched=matched,
            unresolved=unresolved,
            conflict=conflict,
        )
        verification_status = (
            VerificationStatus.CONFLICT
            if status == LinkStatus.CONFLICT
            else VerificationStatus.UNVERIFIED
        )

        return ContextLinkResult(
            input_id=normalized_input.input_id,
            source_id=normalized_input.source_id,
            captured_at=normalized_input.captured_at,
            content_type=normalized_input.content_type,
            record_type=record_type,
            athlete_id=resolutions[EntityType.ATHLETE].entity_id,
            competition_id=resolutions[EntityType.COMPETITION].entity_id,
            event_id=resolutions[EntityType.EVENT].entity_id,
            link_status=status,
            matched_references=matched,
            unresolved_references=unresolved,
            verification_status=verification_status,
            original_text=normalized_input.original_text,
            original_language=normalized_input.original_language,
            translated_text=normalized_input.translated_text,
            target_language=normalized_input.target_language,
            translation_status=normalized_input.translation_status,
            structured_data=deepcopy(normalized_input.structured_data),
        )

    @staticmethod
    def _identify_record_type(normalized_input: NormalizedInput) -> RecordType:
        data = normalized_input.structured_data or {}
        supplied = data.get("record_type")
        if isinstance(supplied, str):
            try:
                return RecordType(supplied)
            except ValueError:
                return RecordType.UNKNOWN
        if normalized_input.content_type == ContentType.MESSAGE:
            return RecordType.MESSAGE
        if normalized_input.content_type == ContentType.DOCUMENT_TEXT:
            return RecordType.DOCUMENT
        return RecordType.UNKNOWN

    @staticmethod
    def _resolve_entity(
        entity_type: EntityType,
        structured_data: dict[str, object],
        repository: InMemoryContextRepository,
    ) -> _Resolution:
        resolution = _Resolution()
        label = entity_type.value.casefold()
        id_key = f"{label}_id"
        reference_key = f"{label}_reference"
        candidates: set[UUID] = set()

        if id_key in structured_data:
            supplied_id = structured_data[id_key]
            try:
                entity_id = UUID(str(supplied_id))
            except (ValueError, TypeError, AttributeError):
                resolution.unresolved[id_key] = "invalid UUID"
            else:
                if repository.contains(entity_type, entity_id):
                    candidates.add(entity_id)
                    resolution.matched[id_key] = entity_id
                else:
                    resolution.unresolved[id_key] = "no exact entity match"

        if reference_key in structured_data:
            supplied_reference = structured_data[reference_key]
            if not isinstance(supplied_reference, str) or not supplied_reference:
                resolution.unresolved[reference_key] = "invalid exact reference"
            else:
                matches = repository.find_by_reference(
                    entity_type,
                    supplied_reference,
                )
                if len(matches) == 1:
                    candidates.add(matches[0])
                    resolution.matched[reference_key] = matches[0]
                elif len(matches) > 1:
                    resolution.unresolved[reference_key] = (
                        "multiple incompatible exact matches"
                    )
                    resolution.conflict = True
                else:
                    resolution.unresolved[reference_key] = "no exact entity match"

        if len(candidates) == 1:
            resolution.entity_id = next(iter(candidates))
        elif len(candidates) > 1:
            resolution.unresolved[label] = "incompatible explicit references"
            resolution.conflict = True
        return resolution

    @staticmethod
    def _event_competition_conflict(
        resolutions: dict[EntityType, _Resolution],
        repository: InMemoryContextRepository,
    ) -> bool:
        event_id = resolutions[EntityType.EVENT].entity_id
        competition_id = resolutions[EntityType.COMPETITION].entity_id
        if event_id is None or competition_id is None:
            return False
        event = repository.event(event_id)
        return event is not None and event.competition_id != competition_id

    @staticmethod
    def _link_status(
        *,
        record_type: RecordType,
        matched: dict[str, UUID],
        unresolved: dict[str, str],
        conflict: bool,
    ) -> LinkStatus:
        if conflict:
            return LinkStatus.CONFLICT
        if record_type == RecordType.UNKNOWN or not matched:
            return LinkStatus.UNRESOLVED
        if unresolved:
            return LinkStatus.PARTIALLY_LINKED
        return LinkStatus.LINKED


def link_context(
    normalized_input: NormalizedInput,
    context_repository: InMemoryContextRepository,
) -> ContextLinkResult:
    """Convenience wrapper for deterministic context linking."""

    return ContextLinkingService().link_context(
        normalized_input,
        context_repository,
    )
