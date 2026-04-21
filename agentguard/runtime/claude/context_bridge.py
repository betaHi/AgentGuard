"""Bridge Claude context-usage snapshots into AgentGuard trace metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span


def _value(source: Any, key: str, default: Any = None) -> Any:
    """Read a field from either an object or mapping."""
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _copy_mapping_items(value: Any) -> dict[str, Any] | None:
    """Copy mapping-like values into plain dictionaries."""
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
        return dict(value.items())
    return None


def _list_count(value: Any) -> int:
    """Return a stable item count for list-like context fields."""
    if isinstance(value, list):
        return len(value)
    return 0


class ClaudeContextBridge:
    """Persist Claude context usage snapshots for later diagnostics."""

    def __init__(self, client: Any, trace: ExecutionTrace, root_span: Span) -> None:
        self._client = client
        self._trace = trace
        self._root_span = root_span

    def capture_snapshot(self, stage: str, message: Any | None = None) -> dict[str, Any] | None:
        """Capture one context-usage snapshot when the client exposes it."""
        getter = getattr(self._client, "get_context_usage", None)
        if getter is None:
            return None
        response = getter()
        if response is None:
            return None

        snapshot = {
            "captured_at": datetime.now(UTC).isoformat(),
            "stage": stage,
            "message_uuid": _value(message, "uuid"),
            "task_id": _value(message, "task_id"),
            "total_tokens": _value(response, "totalTokens"),
            "max_tokens": _value(response, "maxTokens"),
            "raw_max_tokens": _value(response, "rawMaxTokens"),
            "percentage": _value(response, "percentage"),
            "model": _value(response, "model"),
            "auto_compact_enabled": _value(response, "isAutoCompactEnabled"),
            "auto_compact_threshold": _value(response, "autoCompactThreshold"),
            "categories": _value(response, "categories") or [],
            "memory_file_count": _list_count(_value(response, "memoryFiles")),
            "mcp_tool_count": _list_count(_value(response, "mcpTools")),
            "agent_count": _list_count(_value(response, "agents")),
            "message_breakdown": _copy_mapping_items(_value(response, "messageBreakdown")),
            "api_usage": _copy_mapping_items(_value(response, "apiUsage")),
        }
        snapshots = self._trace.metadata.setdefault("claude.context_usage", [])
        snapshots.append(snapshot)
        self._root_span.metadata["claude.context_usage.latest_percentage"] = snapshot["percentage"]
        self._root_span.metadata["claude.context_usage.latest_total_tokens"] = snapshot["total_tokens"]
        return snapshot