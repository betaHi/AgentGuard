"""Claude live runtime adapter for AgentGuard traces."""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.runtime.claude.context_bridge import ClaudeContextBridge
from agentguard.runtime.claude.hook_bridge import ClaudeHookBridge
from agentguard.runtime.claude.task_bridge import ClaudeTaskBridge


def _load_sdk_module() -> Any:
    """Import the Claude SDK lazily."""
    import claude_agent_sdk as sdk

    return sdk


def _value(source: Any, key: str, default: Any = None) -> Any:
    """Read a field from either an object or mapping."""
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _prompt_input(prompt: str | AsyncIterable[dict[str, Any]]) -> dict[str, Any]:
    """Serialize the live query prompt for trace input."""
    if isinstance(prompt, str):
        return {"prompt": prompt}
    return {"prompt_stream": True}


def _text_chunks(value: Any) -> list[str]:
    """Collect text-like chunks from Claude message payloads."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        chunks: list[str] = []
        for key in ("text", "message", "content", "summary"):
            if key in value:
                chunks.extend(_text_chunks(value[key]))
        return chunks
    if isinstance(value, (list, tuple)):
        chunks: list[str] = []
        for item in value:
            chunks.extend(_text_chunks(item))
        return chunks
    for attr in ("text", "content", "thinking"):
        if hasattr(value, attr):
            return _text_chunks(getattr(value, attr))
    return []


def _assistant_summary(message: Any) -> str:
    """Build a short summary for assistant outputs."""
    content = _value(message, "content", _value(message, "message"))
    text = " ".join(chunk.strip() for chunk in _text_chunks(content) if chunk and chunk.strip())
    return text[:500]


class ClaudeRuntimeAdapter:
    """Capture Claude live runtime activity as an AgentGuard trace."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._trace: ExecutionTrace | None = None
        self._root_span: Span | None = None
        self._task_bridge: ClaudeTaskBridge | None = None
        self._hook_bridge: ClaudeHookBridge | None = None
        self._context_bridge: ClaudeContextBridge | None = None
        self._hooks_installed = False
        self._seen_messages: set[str] = set()

    def current_trace(self) -> ExecutionTrace | None:
        """Return the currently accumulated trace."""
        return self._trace

    def start_query(self, prompt: str | AsyncIterable[dict[str, Any]], session_id: str) -> ExecutionTrace:
        """Initialize a new live trace for an outgoing Claude query."""
        task = prompt[:120] if isinstance(prompt, str) and prompt.strip() else f"Claude live session {session_id}"
        self._trace = ExecutionTrace(task=task, trigger="claude_sdk_live")
        self._trace.metadata["runtime"] = "claude_sdk"
        self._trace.metadata["claude.session_id"] = session_id
        self._root_span = Span(
            trace_id=self._trace.trace_id,
            span_type=SpanType.AGENT,
            name="claude-session",
            input_data=_prompt_input(prompt),
            metadata={"runtime": "claude_sdk", "claude.scope": "session"},
        )
        self._trace.add_span(self._root_span)
        self._task_bridge = ClaudeTaskBridge(self._trace, self._root_span)
        self._hook_bridge = ClaudeHookBridge(self._trace, self._root_span, self._task_bridge)
        self._context_bridge = ClaudeContextBridge(self._client, self._trace, self._root_span)
        self._seen_messages.clear()
        self._capture_context_usage("query_start")
        return self._trace

    def install_hooks(self) -> None:
        """Install AgentGuard hook matchers without replacing user hooks."""
        if self._hooks_installed:
            return
        sdk = _load_sdk_module()
        hooks = dict(getattr(self._client.options, "hooks", None) or {})
        for event_name in ("PreToolUse", "PostToolUse", "PostToolUseFailure", "SubagentStart", "SubagentStop"):
            existing = list(hooks.get(event_name, []))
            existing.append(sdk.HookMatcher(matcher="*", hooks=[self._hook_callback]))
            hooks[event_name] = existing
        self._client.options.hooks = hooks
        self._hooks_installed = True

    async def _hook_callback(self, hook_input: Any, _matcher: str | None, _context: Any) -> dict[str, Any]:
        """Convert Claude hook callbacks into trace spans."""
        if self._hook_bridge is None:
            return {}
        event_name = str(_value(hook_input, "hook_event_name", ""))
        if event_name == "PreToolUse":
            self._hook_bridge.handle_pre_tool_use(hook_input)
        elif event_name == "PostToolUse":
            self._hook_bridge.handle_post_tool_use(hook_input)
        elif event_name == "PostToolUseFailure":
            self._hook_bridge.handle_post_tool_use_failure(hook_input)
        elif event_name == "SubagentStart":
            self._hook_bridge.handle_subagent_start(hook_input)
        elif event_name == "SubagentStop":
            self._hook_bridge.handle_subagent_stop(hook_input)
        return {}

    def ingest_message(self, message: Any) -> None:
        """Ingest one Claude runtime message into the active trace."""
        if self._trace is None or self._root_span is None or self._task_bridge is None:
            return
        message_key = self._message_key(message)
        if message_key and message_key in self._seen_messages:
            return
        if message_key:
            self._seen_messages.add(message_key)
        if self._is_task_notification(message):
            self._task_bridge.handle_notification(message)
            self._capture_context_usage("task_notification", message)
        elif self._is_task_progress(message):
            self._task_bridge.handle_progress(message)
            self._capture_context_usage("task_progress", message)
        elif self._is_task_started(message):
            self._task_bridge.handle_started(message)
            self._capture_context_usage("task_started", message)
        elif self._is_assistant_message(message):
            self._add_assistant_span(message)
            self._capture_context_usage("assistant_message", message)
        elif self._is_result_message(message):
            self._capture_context_usage("result", message)
            self._attach_result(message)
        elif self._is_rate_limit_event(message):
            self._append_rate_limit(message)

    def _message_key(self, message: Any) -> str:
        """Build a best-effort dedupe key for live Claude messages."""
        message_uuid = _value(message, "uuid")
        if message_uuid:
            return f"{type(message).__name__}:{message_uuid}"
        return ""

    def _is_task_started(self, message: Any) -> bool:
        return _value(message, "task_id") is not None and _value(message, "status") is None and _value(message, "usage") is None

    def _is_task_progress(self, message: Any) -> bool:
        return _value(message, "task_id") is not None and _value(message, "usage") is not None and _value(message, "status") is None

    def _is_task_notification(self, message: Any) -> bool:
        return _value(message, "task_id") is not None and _value(message, "status") is not None

    def _is_assistant_message(self, message: Any) -> bool:
        return _value(message, "model") is not None and _value(message, "content") is not None

    def _is_result_message(self, message: Any) -> bool:
        return _value(message, "duration_ms") is not None and _value(message, "num_turns") is not None

    def _is_rate_limit_event(self, message: Any) -> bool:
        return _value(message, "rate_limit_info") is not None

    def _add_assistant_span(self, message: Any) -> None:
        """Record one assistant response as an LLM span."""
        assert self._trace is not None and self._root_span is not None and self._task_bridge is not None
        parent_span_id = self._task_bridge.parent_span_id_for_tool_use(_value(message, "parent_tool_use_id")) or self._root_span.span_id
        span = Span(
            trace_id=self._trace.trace_id,
            parent_span_id=parent_span_id,
            span_type=SpanType.LLM_CALL,
            name="assistant-message",
            input_data={"summary": _assistant_summary(message)},
            output_data={"content": _value(message, "content")},
            metadata={
                "runtime": "claude_sdk",
                "claude.scope": "assistant_message",
                "claude.message_uuid": _value(message, "uuid"),
                "claude.model": _value(message, "model"),
                "claude.parent_tool_use_id": _value(message, "parent_tool_use_id"),
            },
        )
        usage = _value(message, "usage") or {}
        span.token_count = _value(usage, "output_tokens") or _value(usage, "input_tokens")
        span.complete(span.output_data)
        self._trace.add_span(span)

    def _attach_result(self, message: Any) -> None:
        """Attach final run result metadata and close the root span."""
        assert self._trace is not None and self._root_span is not None
        self._trace.metadata["claude.result"] = _value(message, "result")
        self._trace.metadata["claude.stop_reason"] = _value(message, "stop_reason")
        self._trace.metadata["claude.total_cost_usd"] = _value(message, "total_cost_usd")
        self._trace.metadata["claude.usage"] = _value(message, "usage")
        self._trace.metadata["claude.model_usage"] = _value(message, "model_usage")
        self._trace.metadata["claude.permission_denials"] = _value(message, "permission_denials")
        self._root_span.estimated_cost_usd = _value(message, "total_cost_usd")
        self._root_span.output_data = {
            "result": _value(message, "result"),
            "structured_output": _value(message, "structured_output"),
        }
        if _value(message, "is_error"):
            self._root_span.fail(str((_value(message, "errors") or ["Claude query failed"])[0]))
            self._trace.fail(self._root_span.error or "Claude query failed")
            return
        self._root_span.complete(self._root_span.output_data)
        self._trace.complete()

    def _append_rate_limit(self, message: Any) -> None:
        """Persist rate-limit events as trace metadata for later diagnostics."""
        assert self._trace is not None
        events = self._trace.metadata.setdefault("claude.rate_limits", [])
        events.append(_value(message, "rate_limit_info"))

    def _capture_context_usage(self, stage: str, message: Any | None = None) -> None:
        """Capture context-usage metadata when the wrapped client exposes it."""
        if self._context_bridge is None:
            return
        self._context_bridge.capture_snapshot(stage, message)