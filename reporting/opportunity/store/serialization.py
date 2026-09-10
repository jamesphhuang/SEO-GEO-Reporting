"""Canonical serialization helpers for the offline immutable stores."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from typing import Any, Mapping


class SerializationError(ValueError):
    """Raised when a record cannot be represented safely and deterministically."""


def _reject_non_finite(value: Any, path: str = "record") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise SerializationError(f"non-finite number at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_non_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_non_finite(item, f"{path}[{index}]")


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def canonical_json(value: Mapping[str, Any]) -> str:
    """Return the one canonical JSON representation used in files and hashes."""

    _reject_non_finite(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    )


def content_hash(record: Mapping[str, Any]) -> str:
    """Hash semantic fields while excluding runtime/review-only fields."""

    excluded = {
        "content_hash",
        "created_at",
        "updated_at",
        "status",
        "review_state",
        "review_event_ref",
    }
    semantic = {key: value for key, value in record.items() if key not in excluded}
    return hashlib.sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


def canonical_line(record: Mapping[str, Any]) -> str:
    return canonical_json(record) + "\n"
