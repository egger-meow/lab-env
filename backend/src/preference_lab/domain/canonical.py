"""Canonical JSON serialization and hashing according to PREFERENCE_LAB_SPEC.md."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _assert_no_nan_or_inf(obj: Any) -> None:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError(f"NaN and Infinity are not permitted in canonical JSON: {obj}")
    elif isinstance(obj, dict):
        for v in obj.values():
            _assert_no_nan_or_inf(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _assert_no_nan_or_inf(item)


def canonical_json_str(data: Any) -> str:
    """Serialize data into a deterministic canonical JSON string.

    Rules from spec:
    - Sorted keys
    - Fixed separators (",", ":")
    - UTF-8 representation
    - ensure_ascii=False
    - No NaN / Infinity
    """
    _assert_no_nan_or_inf(data)
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize data into UTF-8 canonical JSON bytes."""
    return canonical_json_str(data).encode("utf-8")


def sha256_canonical_json(data: Any) -> str:
    """Compute hex SHA-256 hash of canonical JSON representation."""
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()
