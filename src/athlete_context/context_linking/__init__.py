"""Context Linking layer exports."""

from athlete_context.context_linking.models import (
    ContextLinkResult,
    EntityType,
    ExactReference,
    LinkStatus,
    RecordType,
)
from athlete_context.context_linking.repository import InMemoryContextRepository
from athlete_context.context_linking.service import (
    ContextLinkingService,
    link_context,
)

__all__ = [
    "ContextLinkResult",
    "ContextLinkingService",
    "EntityType",
    "ExactReference",
    "InMemoryContextRepository",
    "LinkStatus",
    "RecordType",
    "link_context",
]
