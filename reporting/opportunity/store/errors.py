"""Stable, non-sensitive errors raised by the immutable stores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class StoreError:
    code: str
    field: str
    message: str
    severity: str = "ERROR"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
        }


class ImmutableStoreError(ValueError):
    """A deterministic validation or integrity failure before append."""

    def __init__(self, code: str, message: str, field: str = "record", *, errors: Optional[list[StoreError]] = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.field = field
        self.message = message
        self.errors = errors or [StoreError(code, field, message)]

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "field": self.field, "message": self.message, "errors": [e.as_dict() for e in self.errors]}
