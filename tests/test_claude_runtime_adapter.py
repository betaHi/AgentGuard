"""Tests for Claude live runtime capture."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from agentguard.core.trace import SpanStatus, SpanType
from agentguard.runtime.claude import wrap_claude_client


@dataclass
class FakeHookMatcher:
    matcher: str | None = None
    hooks: list[Any] = field(default_factory=list)
    timeout: float | None = None


@dataclass
class FakeAssistantMessage:
    content: list[dict[str, Any]]
    model: str
    uuid: str
    session_id: str
    parent_tool_use_id: str | None = None
    usage: dict[str, Any] | None = None


@dataclass
class FakeTaskStartedMessage:
    task_id: str
    description: str
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    task_type: str | None = None
    usage: dict[str, Any] | None = None
    status: str | None = None


@dataclass
class FakeTaskProgressMessage:
    task_id: str
    description: str
    usage: dict[str, Any]
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    last_tool_name: str | None = None
    status: str | None = None


@dataclass
class FakeTaskNotificationMessage:
    task_id: str
    status: str
    output_file: str
    summary: str
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    usage: dict[str, Any] | None = None


@dataclass
class FakeResultMessage:
    duration_ms: int
    num_turns: int
    is_error: bool
    session_id: str
    result: str | None = None
    structured_output: Any = None
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None
    model_usage: dict[str, Any] | None = None
    permission_denials: list[Any] | None = None
    errors: list[str] | None = None
    stop_reason: str | None = None
    uuid: str | None = None


@dataclass
class FakeRateLimitInfo:
    status: str
    resets_at: int | None = None
    rate_limit_type: str | None = None
    utilization: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeRateLimitEvent:
    rate_limit_info: FakeRateLimitInfo
    uuid: str
    session_id: str


class FakeClaudeSDKClient:
    """Small async test double for the wrapped Claude client."""

    def __init__(
        self,
        messages: list[Any],
        hooks: dict[str, list[Any]] | None = None,
        context_usage: dict[str, Any] | None = None,
    ) -> None:
        self.options = SimpleNamespace(hooks=hooks)
        self._messages = list(messages)
        self.query_calls: list[tuple[Any, str]] = []
        self.entered = False
        self.exited = False
        self.context_usage = context_usage

    async def __aenter__(self) -> FakeClaudeSDKClient:
        self.entered = True
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.exited = True

    async def query(self, prompt: Any, session_id: str = "default") -> None:
        self.query_calls.append((prompt, session_id))

    async def receive_response(self) -> AsyncIterator[Any]:
        for message in self._messages:
            yield message

    async def receive_messages(self) -> AsyncIterator[Any]:
        for message in self._messages:
            yield message

    def get_context_usage(self) -> dict[str, Any] | None:
        return self.context_usage


def _installed_callback(client: FakeClaudeSDKClient, event_name: str):
    matcher = client.options.hooks[event_name][-1]
    return matcher.hooks[0]


@pytest.mark.anyio
async def test_wrap_claude_client_captures_live_runtime(monkeypatch):
    sdk_stub = SimpleNamespace(HookMatcher=FakeHookMatcher)
    monkeypatch.setattr("agentguard.runtime.claude.adapter._load_sdk_module", lambda: sdk_stub)

    messages = [
        FakeTaskStartedMessage(
            task_id="task-1",
            description="reviewer",
            uuid="task-start-1",
            session_id="sess-live",
            tool_use_id="task-tool-1",
        ),
        FakeTaskProgressMessage(
            task_id="task-1",
            description="reviewer",
            usage={"total_tokens": 321, "tool_uses": 1, "duration_ms": 1200},
            uuid="task-progress-1",
            session_id="sess-live",
            tool_use_id="task-tool-1",
            last_tool_name="Read",
        ),
        FakeAssistantMessage(
            content=[{"text": "Reviewed the patch and proposed one change."}],
            model="claude-sonnet",
            uuid="assistant-1",
            session_id="sess-live",
            parent_tool_use_id="task-tool-1",
            usage={"output_tokens": 111},
        ),
        FakeTaskNotificationMessage(
            task_id="task-1",
            status="completed",
            output_file="/tmp/reviewer.md",
            summary="Reviewer finished successfully",
            uuid="task-done-1",
            session_id="sess-live",
            tool_use_id="task-tool-1",
            usage={"total_tokens": 456, "tool_uses": 1, "duration_ms": 1800},
        ),
        FakeResultMessage(
            duration_ms=2400,
            num_turns=2,
            is_error=False,
            session_id="sess-live",
            result="Completed auth refactor run",
            total_cost_usd=0.12,
            usage={"input_tokens": 500, "output_tokens": 700},
            uuid="result-1",
        ),
    ]
    raw_client = FakeClaudeSDKClient(messages)
    client = wrap_claude_client(raw_client)

    async with client as wrapped:
        await wrapped.query("Refactor the auth module", session_id="sess-live")
        pre_tool = _installed_callback(raw_client, "PreToolUse")
        post_tool = _installed_callback(raw_client, "PostToolUse")
        await pre_tool(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "sess-live",
                "tool_name": "Read",
                "tool_input": {"file_path": "auth.py"},
                "tool_use_id": "tool-1",
                "agent_id": "reviewer-agent",
                "agent_type": "reviewer",
            },
            None,
            {},
        )
        await post_tool(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-live",
                "tool_name": "Read",
                "tool_input": {"file_path": "auth.py"},
                "tool_response": {"content": "patched file"},
                "tool_use_id": "tool-1",
                "agent_id": "reviewer-agent",
                "agent_type": "reviewer",
            },
            None,
            {},
        )
        async for _message in wrapped.receive_response():
            pass

    trace = client.agentguard_trace()
    assert trace is not None
    assert trace.metadata["claude.session_id"] == "sess-live"
    assert trace.metadata["claude.total_cost_usd"] == 0.12
    assert trace.status == SpanStatus.COMPLETED
    assert any(span.name == "reviewer" and span.span_type == SpanType.AGENT for span in trace.spans)
    assert any(span.name == "Read" and span.span_type == SpanType.TOOL for span in trace.spans)
    assert any(span.span_type == SpanType.LLM_CALL for span in trace.spans)
    assert raw_client.query_calls == [("Refactor the auth module", "sess-live")]
    assert raw_client.entered is True and raw_client.exited is True


@pytest.mark.anyio
async def test_wrap_claude_client_captures_context_usage_and_rich_result_metadata(monkeypatch):
    sdk_stub = SimpleNamespace(HookMatcher=FakeHookMatcher)
    monkeypatch.setattr("agentguard.runtime.claude.adapter._load_sdk_module", lambda: sdk_stub)

    raw_client = FakeClaudeSDKClient(
        messages=[
            FakeTaskStartedMessage(
                task_id="task-ctx-1",
                description="reviewer",
                uuid="task-ctx-start-1",
                session_id="sess-ctx",
                tool_use_id="task-tool-ctx-1",
            ),
            FakeRateLimitEvent(
                rate_limit_info=FakeRateLimitInfo(
                    status="allowed_warning",
                    resets_at=123456,
                    rate_limit_type="five_hour",
                    utilization=0.82,
                    raw={"source": "sdk"},
                ),
                uuid="rate-limit-1",
                session_id="sess-ctx",
            ),
            FakeResultMessage(
                duration_ms=1800,
                num_turns=2,
                is_error=False,
                session_id="sess-ctx",
                result="Completed context-heavy run",
                total_cost_usd=0.09,
                usage={"input_tokens": 400, "output_tokens": 500},
                model_usage={"sonnet": {"input_tokens": 400, "output_tokens": 500}},
                permission_denials=[{"tool": "Bash", "reason": "policy"}],
                uuid="result-ctx-1",
            ),
        ],
        context_usage={
            "totalTokens": 15000,
            "maxTokens": 200000,
            "rawMaxTokens": 200000,
            "percentage": 7.5,
            "model": "claude-sonnet",
            "isAutoCompactEnabled": True,
            "memoryFiles": [{"path": "memory.md"}],
            "mcpTools": [{"name": "fetch"}, {"name": "search"}],
            "agents": [{"name": "reviewer"}],
            "categories": [{"name": "messages", "tokens": 12000}],
            "messageBreakdown": {"assistant": 9000, "user": 6000},
            "apiUsage": {"requests": 3},
        },
    )
    client = wrap_claude_client(raw_client)

    await client.query("Inspect context growth", session_id="sess-ctx")
    async for _message in client.receive_messages():
        pass

    trace = client.agentguard_trace()
    assert trace is not None
    snapshots = trace.metadata["claude.context_usage"]
    assert snapshots
    assert snapshots[0]["stage"] == "query_start"
    assert snapshots[0]["percentage"] == 7.5
    assert snapshots[0]["memory_file_count"] == 1
    assert snapshots[0]["mcp_tool_count"] == 2
    assert trace.metadata["claude.model_usage"] == {"sonnet": {"input_tokens": 400, "output_tokens": 500}}
    assert trace.metadata["claude.permission_denials"] == [{"tool": "Bash", "reason": "policy"}]
    assert trace.metadata["claude.rate_limits"][0].status == "allowed_warning"


@pytest.mark.anyio
async def test_wrap_claude_client_preserves_existing_hooks(monkeypatch):
    sdk_stub = SimpleNamespace(HookMatcher=FakeHookMatcher)
    monkeypatch.setattr("agentguard.runtime.claude.adapter._load_sdk_module", lambda: sdk_stub)

    existing = FakeHookMatcher(matcher="existing", hooks=[object()])
    raw_client = FakeClaudeSDKClient(messages=[], hooks={"PreToolUse": [existing]})
    client = wrap_claude_client(raw_client)

    await client.query("Inspect auth flow", session_id="sess-hooks")

    installed = raw_client.options.hooks["PreToolUse"]
    assert installed[0] is existing
    assert len(installed) == 2


@pytest.mark.anyio
async def test_wrap_claude_client_marks_failed_result(monkeypatch):
    sdk_stub = SimpleNamespace(HookMatcher=FakeHookMatcher)
    monkeypatch.setattr("agentguard.runtime.claude.adapter._load_sdk_module", lambda: sdk_stub)

    raw_client = FakeClaudeSDKClient(
        messages=[
            FakeResultMessage(
                duration_ms=900,
                num_turns=1,
                is_error=True,
                session_id="sess-fail",
                errors=["permission denied"],
                uuid="result-fail-1",
            )
        ]
    )
    client = wrap_claude_client(raw_client)

    await client.query("Run protected action", session_id="sess-fail")
    async for _message in client.receive_messages():
        pass

    trace = client.agentguard_trace()
    assert trace is not None
    assert trace.status == SpanStatus.FAILED
    assert trace.agent_spans[0].status == SpanStatus.FAILED
    assert trace.agent_spans[0].error == "permission denied"