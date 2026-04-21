"""Bridge Claude task lifecycle messages into AgentGuard spans."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _value(source: Any, key: str, default: Any = None) -> Any:
    """Read a field from either an object or mapping."""
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _usage_metadata(message: Any) -> dict[str, Any]:
    """Extract compact usage metadata from task messages."""
    usage = _value(message, "usage") or {}
    return {
        "claude.task.total_tokens": _value(usage, "total_tokens"),
        "claude.task.tool_uses": _value(usage, "tool_uses"),
        "claude.task.duration_ms": _value(usage, "duration_ms"),
    }


def _status_from_notification(message: Any) -> SpanStatus:
    """Map Claude task notification statuses to AgentGuard statuses."""
    status = str(_value(message, "status", "completed"))
    if status == "failed":
        return SpanStatus.FAILED
    if status == "stopped":
        return SpanStatus.TIMEOUT
    return SpanStatus.COMPLETED


def _finish_span(span: Span, status: SpanStatus, output_data: dict[str, Any], error: str | None) -> None:
    """Finish a task span while preserving non-completed statuses."""
    if status == SpanStatus.COMPLETED:
        span.complete(output_data)
        return
    span.status = status
    span.output_data = output_data
    span.error = error
    span.ended_at = datetime.now(UTC).isoformat()


class ClaudeTaskBridge:
    """Track Claude task messages as AgentGuard agent spans."""

    def __init__(self, trace: ExecutionTrace, root_span: Span) -> None:
        self._trace = trace
        self._root_span = root_span
        self._task_spans: dict[str, Span] = {}
        self._tool_use_parents: dict[str, str] = {}

    def parent_span_id_for_tool_use(self, tool_use_id: str | None) -> str | None:
        """Resolve the span parent associated with a task tool use id."""
        if not tool_use_id:
            return None
        return self._tool_use_parents.get(tool_use_id)

    def handle_started(self, message: Any) -> Span:
        """Create or return the span for a task start event."""
        task_id = str(_value(message, "task_id", ""))
        existing = self._task_spans.get(task_id)
        if existing is not None:
            return existing

        tool_use_id = _value(message, "tool_use_id")
        parent_span_id = self.parent_span_id_for_tool_use(tool_use_id) or self._root_span.span_id
        span = Span(
            trace_id=self._trace.trace_id,
            parent_span_id=parent_span_id,
            span_type=SpanType.AGENT,
            name=str(_value(message, "description", task_id or "claude-task")),
            metadata={
                "runtime": "claude_sdk",
                "claude.scope": "task",
                "claude.task_id": task_id,
                "claude.session_id": _value(message, "session_id"),
                "claude.tool_use_id": tool_use_id,
                "claude.task_type": _value(message, "task_type"),
                "claude.message_uuid": _value(message, "uuid"),
            },
        )
        self._trace.add_span(span)
        self._task_spans[task_id] = span
        if tool_use_id:
            self._tool_use_parents[str(tool_use_id)] = span.span_id
        return span

    def handle_progress(self, message: Any) -> Span:
        """Update task metadata from progress messages."""
        span = self.handle_started(message)
        span.metadata.update({k: v for k, v in _usage_metadata(message).items() if v is not None})
        last_tool_name = _value(message, "last_tool_name")
        if last_tool_name:
            span.metadata["claude.task.last_tool_name"] = last_tool_name
        return span

    def handle_notification(self, message: Any) -> Span:
        """Complete a task span from a terminal notification."""
        span = self.handle_progress(message)
        span.token_count = _value(_value(message, "usage") or {}, "total_tokens")
        output_data = {
            "summary": _value(message, "summary"),
            "output_file": _value(message, "output_file"),
        }
        span.metadata["claude.task.status"] = _value(message, "status")
        status = _status_from_notification(message)
        error = None if status == SpanStatus.COMPLETED else str(_value(message, "summary", "Claude task failed"))
        _finish_span(span, status, output_data, error)
        return span