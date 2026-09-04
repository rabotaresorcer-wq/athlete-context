"""In-memory exact-match repository used by the Context Linking layer."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from athlete_context.context_linking.models import EntityType, ExactReference
from athlete_context.domain import Athlete, Competition, Event


class InMemoryContextRepository:
    """Immutable snapshots of known entities and their explicit references."""

    def __init__(
        self,
        *,
        athletes: Iterable[Athlete] = (),
        competitions: Iterable[Competition] = (),
        events: Iterable[Event] = (),
        exact_references: Iterable[ExactReference] = (),
    ) -> None:
        self._athletes = {entity.id: entity for entity in athletes}
        self._competitions = {entity.id: entity for entity in competitions}
        self._events = {entity.id: entity for entity in events}

        references: dict[tuple[EntityType, str], set[UUID]] = defaultdict(set)
        for exact_reference in exact_references:
            references[
                (exact_reference.entity_type, exact_reference.reference)
            ].add(exact_reference.entity_id)
        self._references = {
            key: tuple(sorted(entity_ids, key=str))
            for key, entity_ids in references.items()
        }

    def contains(self, entity_type: EntityType, entity_id: UUID) -> bool:
        return entity_id in self._entities(entity_type)

    def event(self, event_id: UUID) -> Event | None:
        return self._events.get(event_id)

    def find_by_reference(
        self, entity_type: EntityType, reference: str
    ) -> tuple[UUID, ...]:
        candidates = self._references.get((entity_type, reference), ())
        return tuple(
            entity_id
            for entity_id in candidates
            if entity_id in self._entities(entity_type)
        )

    def _entities(self, entity_type: EntityType) -> dict[UUID, object]:
        if entity_type == EntityType.ATHLETE:
            return self._athletes
        if entity_type == EntityType.COMPETITION:
            return self._competitions
        return self._events
