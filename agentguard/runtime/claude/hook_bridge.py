"""Bridge Claude SDK hook callbacks into AgentGuard spans."""

from __future__ import annotations

from typing import Any

from agentguard.core.trace import ExecutionTrace, Span, SpanType


def _value(source: Any, key: str, default: Any = None) -> Any:
    """Read a field from either an object or mapping."""
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


class ClaudeHookBridge:
    """Track tool and subagent hook events as spans."""

    def __init__(self, trace: ExecutionTrace, root_span: Span, task_bridge: Any) -> None:
        self._trace = trace
        self._root_span = root_span
        self._task_bridge = task_bridge
        self._tool_spans: dict[str, Span] = {}
        self._subagent_spans: dict[str, Span] = {}

    def parent_span_id_for_tool_use(self, tool_use_id: str | None) -> str | None:
        """Resolve the best known parent span for a tool use id."""
        if not tool_use_id:
            return None
        parent = self._task_bridge.parent_span_id_for_tool_use(tool_use_id)
        if parent:
            return parent
        span = self._tool_spans.get(str(tool_use_id))
        return span.parent_span_id if span is not None else None

    def handle_pre_tool_use(self, hook_input: Any) -> Span:
        """Start a tool span on a PreToolUse event."""
        tool_use_id = str(_value(hook_input, "tool_use_id", ""))
        existing = self._tool_spans.get(tool_use_id)
        if existing is not None:
            return existing

        parent_span_id = self._subagent_parent(hook_input) or self._root_span.span_id
        span = Span(
            trace_id=self._trace.trace_id,
            parent_span_id=parent_span_id,
            span_type=SpanType.TOOL,
            name=str(_value(hook_input, "tool_name", "tool")),
            input_data=_value(hook_input, "tool_input"),
            metadata={
                "runtime": "claude_sdk",
                "claude.scope": "tool_hook",
                "claude.tool_use_id": tool_use_id,
                "claude.agent_id": _value(hook_input, "agent_id"),
                "claude.agent_type": _value(hook_input, "agent_type"),
                "claude.session_id": _value(hook_input, "session_id"),
            },
        )
        self._trace.add_span(span)
        self._tool_spans[tool_use_id] = span
        return span

    def handle_post_tool_use(self, hook_input: Any) -> Span:
        """Complete a tool span from a successful hook."""
        span = self.handle_pre_tool_use(hook_input)
        span.complete(_value(hook_input, "tool_response"))
        return span

    def handle_post_tool_use_failure(self, hook_input: Any) -> Span:
        """Fail a tool span from a failed hook."""
        span = self.handle_pre_tool_use(hook_input)
        span.fail(str(_value(hook_input, "error", "Claude tool failed")))
        return span

    def handle_subagent_start(self, hook_input: Any) -> Span:
        """Create a subagent span when the SDK emits a subagent start hook."""
        agent_id = str(_value(hook_input, "agent_id", ""))
        existing = self._subagent_spans.get(agent_id)
        if existing is not None:
            return existing

        span = Span(
            trace_id=self._trace.trace_id,
            parent_span_id=self._root_span.span_id,
            span_type=SpanType.AGENT,
            name=str(_value(hook_input, "agent_type", agent_id or "subagent")),
            metadata={
                "runtime": "claude_sdk",
                "claude.scope": "subagent_hook",
                "claude.agent_id": agent_id,
                "claude.agent_type": _value(hook_input, "agent_type"),
                "claude.session_id": _value(hook_input, "session_id"),
            },
        )
        self._trace.add_span(span)
        self._subagent_spans[agent_id] = span
        return span

    def handle_subagent_stop(self, hook_input: Any) -> Span | None:
        """Complete an active subagent hook span if one exists."""
        agent_id = str(_value(hook_input, "agent_id", ""))
        span = self._subagent_spans.get(agent_id)
        if span is None:
            return None
        span.complete({"transcript_path": _value(hook_input, "agent_transcript_path")})
        return span

    def _subagent_parent(self, hook_input: Any) -> str | None:
        """Resolve tool parentage from active subagent spans or task linkage."""
        agent_id = str(_value(hook_input, "agent_id", ""))
        subagent = self._subagent_spans.get(agent_id)
        if subagent is not None:
            return subagent.span_id
        return self.parent_span_id_for_tool_use(_value(hook_input, "tool_use_id"))