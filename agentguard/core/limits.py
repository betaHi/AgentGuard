"""Trace size limits and truncation for production safety.

Why: Unbounded traces with large metadata/input_data/output_data can
cause OOM during serialization or crash downstream consumers. This module
provides fail-safe size checking and truncation.

Constants:
    TRACE_WARN_BYTES: Warn threshold (10 MB).
    SPAN_DATA_MAX_BYTES: Per-span data field truncation limit (100 KB).
    TRUNCATION_MARKER: Marker appended to truncated strings.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_logger = logging.getLogger(__name__)

TRACE_WARN_BYTES: int = 10 * 1024 * 1024  # 10 MB
SPAN_DATA_MAX_BYTES: int = 100 * 1024  # 100 KB per field
TRUNCATION_MARKER: str = "...[truncated by AgentGuard]"


def check_trace_size(trace_dict: dict[str, Any]) -> int:
    """Check serialized trace size and warn if over threshold.

    Args:
        trace_dict: The trace as a plain dict (from to_dict()).

    Returns:
        Approximate size in bytes.
    """
    size = len(json.dumps(trace_dict, default=str).encode("utf-8"))
    from agentguard.settings import get_settings
    warn_bytes = int(get_settings().max_trace_size_mb * 1024 * 1024)
    if size > warn_bytes:
        _logger.warning(
            "Trace '%s' is %.1f MB (limit: %.1f MB). "
            "Consider truncating metadata or reducing span data.",
            trace_dict.get("task", "unknown"),
            size / (1024 * 1024),
            warn_bytes / (1024 * 1024),
        )
    return size


def truncate_trace(trace_dict: dict[str, Any]) -> dict[str, Any]:
    """Truncate oversized span data fields to fit within limits.

    Modifies a copy of trace_dict, truncating input_data, output_data,
    and metadata on each span if they exceed SPAN_DATA_MAX_BYTES.

    Args:
        trace_dict: The trace as a plain dict.

    Returns:
        A new dict with truncated span data where needed.
    """
    result = {**trace_dict}
    if "spans" in result:
        result["spans"] = [_truncate_span(s) for s in result["spans"]]
    return result


def _truncate_span(span_dict: dict[str, Any]) -> dict[str, Any]:
    """Truncate oversized fields on a single span dict."""
    result = {**span_dict}
    for field in ("input_data", "output_data", "metadata"):
        if field in result and result[field] is not None:
            result[field] = _truncate_field(result[field], field)
    return result


def _truncate_field(value: Any, field_name: str) -> Any:
    """Truncate a field value if its JSON size exceeds the limit.

    Args:
        value: The field value to potentially truncate.
        field_name: Name of the field (for logging).

    Returns:
        Original value if within limits, or a truncated version.
    """
    try:
        serialized = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return TRUNCATION_MARKER
    size = len(serialized.encode("utf-8"))
    if size <= SPAN_DATA_MAX_BYTES:
        return value
    _logger.debug(
        "Truncating span field '%s' from %d to %d bytes",
        field_name, size, SPAN_DATA_MAX_BYTES,
    )
    return _truncate_value(value, SPAN_DATA_MAX_BYTES)


def _truncate_value(value: Any, max_bytes: int) -> Any:
    """Recursively truncate a value to fit within max_bytes.

    Strategy:
    - Strings: cut to max_bytes chars + marker
    - Dicts: keep keys, truncate values
    - Lists: keep first N items that fit
    """
    if isinstance(value, str):
        if len(value.encode("utf-8")) > max_bytes:
            cut = max(0, max_bytes - len(TRUNCATION_MARKER.encode("utf-8")))
            return value[:cut] + TRUNCATION_MARKER
        return value
    if isinstance(value, dict):
        return _truncate_dict(value, max_bytes)
    if isinstance(value, list):
        return _truncate_list(value, max_bytes)
    return value


def _truncate_dict(d: dict, max_bytes: int) -> dict:
    """Keep all keys but truncate values to fit."""
    result = {}
    budget = max_bytes
    for k, v in d.items():
        per_key = max(256, budget // max(1, len(d) - len(result)))
        result[k] = _truncate_value(v, per_key)
        budget -= len(json.dumps({k: result[k]}, default=str).encode("utf-8"))
        if budget <= 0:
            result[k] = TRUNCATION_MARKER
            break
    return result


def _truncate_list(lst: list, max_bytes: int) -> list:
    """Keep first N items that fit within budget."""
    result = []
    budget = max_bytes
    for item in lst:
        serialized = json.dumps(item, default=str).encode("utf-8")
        if len(serialized) > budget:
            result.append(TRUNCATION_MARKER)
            break
        result.append(item)
        budget -= len(serialized)
    return result
