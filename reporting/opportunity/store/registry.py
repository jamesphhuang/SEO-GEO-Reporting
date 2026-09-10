"""Small canonical-registry lookup used by the local stores."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..entities import validate_registry
from .errors import ImmutableStoreError


class RegistryLookup:
    def __init__(self, registry: Optional[Mapping[str, Any]]) -> None:
        self.registry = registry
        self._ids: dict[tuple[str, str], Mapping[str, Any]] = {}
        if registry is None:
            return
        result = validate_registry(registry)
        if not result.is_valid:
            raise ImmutableStoreError("INVALID_CANONICAL_REGISTRY", "canonical registry failed WP3 validation")
        for entity_type, rows in registry.get("entities", {}).items():
            suffix = "_id"
            for row in rows:
                for key, value in row.items():
                    if key.endswith(suffix) and isinstance(value, str):
                        self._ids[(entity_type, value)] = row
                        break

    def require(self, entity_type: str, entity_id: str, field: str) -> None:
        if self.registry is None or (entity_type, entity_id) not in self._ids:
            raise ImmutableStoreError("UNRESOLVED_ENTITY", "entity reference is not in the canonical registry", field)

    def has(self, entity_type: str, entity_id: str) -> bool:
        return self.registry is not None and (entity_type, entity_id) in self._ids
