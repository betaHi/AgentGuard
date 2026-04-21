"""Tests for Claude SDK session import."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from agentguard.core.trace import SpanType
from agentguard.runtime.claude.session_import import ClaudeSessionImportError, import_claude_session
from agentguard.runtime.claude.session_import import ClaudeSessionImportError, import_claude_session, list_claude_sessions


@dataclass
class FakeSessionMessage:
    type: str
    uuid: str
    session_id: str
    message: object
    parent_tool_use_id: str | None = None


@dataclass
class FakeSessionInfo:
    session_id: str
    summary: str
    custom_title: str | None = None
    first_prompt: str | None = None
    git_branch: str | None = None


def _sdk_stub(*, include_subagents: bool = True):
    session_messages = [
        FakeSessionMessage(
            type="user",
            uuid="u1",
            session_id="sess-1",
            message={"text": "Refactor the auth flow"},
        ),
        FakeSessionMessage(
            type="assistant",
            uuid="a1",
            session_id="sess-1",
            message={"content": [{"text": "Planned the refactor and called subagent."}]},
        ),
    ]
    namespace = SimpleNamespace(
        get_session_messages=lambda session_id, directory=None: session_messages,
        get_session_info=lambda session_id, directory=None: FakeSessionInfo(
            session_id=session_id,
            summary="Auth refactor session",
            custom_title="auth-refactor",
            first_prompt="Refactor the auth flow",
            git_branch="feature/auth",
        ),
    )
    if include_subagents:
        namespace.list_subagents = lambda session_id, directory=None: ["reviewer"]
        namespace.get_subagent_messages = lambda session_id, agent_id, directory=None: [
            FakeSessionMessage(
                type="user",
                uuid="su1",
                session_id=session_id,
                message={"text": "Review the auth patch"},
            ),
            FakeSessionMessage(
                type="assistant",
                uuid="sa1",
                session_id=session_id,
                message={"content": [{"text": "Found one risky migration edge case."}]},
            ),
        ]
    return namespace


def test_import_claude_session_builds_trace(monkeypatch):
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: _sdk_stub(),
    )

    trace = import_claude_session("sess-1")

    assert trace.trace_id == "sess-1"
    assert trace.task == "Auth refactor session"
    assert trace.metadata["claude.git_branch"] == "feature/auth"
    assert any(span.name == "auth-refactor" for span in trace.agent_spans)
    assert any(span.name == "reviewer" for span in trace.agent_spans)
    assert any(span.span_type == SpanType.HANDOFF and span.handoff_to == "reviewer" for span in trace.spans)
    assert any(span.span_type == SpanType.LLM_CALL for span in trace.spans)


def test_import_claude_session_marks_missing_subagent_helpers(monkeypatch):
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: _sdk_stub(include_subagents=False),
    )

    trace = import_claude_session("sess-1")

    assert trace.metadata["claude.subagents_unavailable"] is True
    assert all(span.name != "reviewer" for span in trace.agent_spans)


def test_import_claude_session_requires_messages(monkeypatch):
    stub = SimpleNamespace(
        get_session_messages=lambda session_id, directory=None: [],
        get_session_info=lambda session_id, directory=None: None,
    )
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: stub,
    )

    with pytest.raises(ClaudeSessionImportError):
        import_claude_session("sess-1")


def test_import_claude_session_fails_when_sdk_missing(monkeypatch):
    def _raise():
        raise ClaudeSessionImportError("sdk missing")

    monkeypatch.setattr("agentguard.runtime.claude.session_import._load_sdk_module", _raise)

    with pytest.raises(ClaudeSessionImportError, match="sdk missing"):
        import_claude_session("sess-1")


def test_import_claude_session_supports_helpers_without_directory_keyword(monkeypatch):
    session_messages = [
        FakeSessionMessage(
            type="user",
            uuid="u1",
            session_id="sess-1",
            message={"text": "Refactor the auth flow"},
        ),
        FakeSessionMessage(
            type="assistant",
            uuid="a1",
            session_id="sess-1",
            message={"content": [{"text": "Finished the refactor."}]},
        ),
    ]
    stub = SimpleNamespace(
        get_session_messages=lambda session_id: tuple(session_messages),
        get_session_info=lambda session_id: {"summary": "Auth refactor session", "custom_title": "auth-refactor"},
        list_subagents=lambda session_id: ("reviewer",),
        get_subagent_messages=lambda session_id, agent_id: [
            FakeSessionMessage(
                type="assistant",
                uuid="sa1",
                session_id=session_id,
                message={"content": [{"text": f"{agent_id} done"}]},
            ),
        ],
    )
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: stub,
    )

    trace = import_claude_session("sess-1", directory="/tmp/claude")

    assert trace.metadata["claude.directory"] == "/tmp/claude"
    assert any(span.name == "reviewer" for span in trace.agent_spans)


def test_import_claude_session_skips_failed_subagent_imports(monkeypatch):
    def test_list_claude_sessions_returns_sorted_summaries(monkeypatch):
        stub = SimpleNamespace(
            list_sessions=lambda directory=None, limit=None, offset=0, include_worktrees=True: [
                {
                    "session_id": "sess-old",
                    "summary": "Old session",
                    "cwd": "/tmp/old",
                    "last_modified": 100,
                    "git_branch": "main",
                },
                {
                    "session_id": "sess-new",
                    "summary": "New session",
                    "cwd": "/tmp/new",
                    "last_modified": 200,
                    "git_branch": "feature",
                    "first_prompt": "Investigate propagation",
                },
            ]
        )
        monkeypatch.setattr(
            "agentguard.runtime.claude.session_import._load_sdk_module",
            lambda: stub,
        )

        sessions = list_claude_sessions(limit=5)

        assert [session.session_id for session in sessions] == ["sess-new", "sess-old"]
        assert sessions[0].to_dict()["cwd"] == "/tmp/new"


    def test_list_claude_sessions_supports_sdk_without_directory_keyword(monkeypatch):
        stub = SimpleNamespace(
            list_sessions=lambda limit=None, offset=0, include_worktrees=True: [
                {"session_id": "sess-1", "summary": "SDK drift", "cwd": "/tmp/project", "last_modified": 123}
            ]
        )
        monkeypatch.setattr(
            "agentguard.runtime.claude.session_import._load_sdk_module",
            lambda: stub,
        )

        sessions = list_claude_sessions(directory="/tmp/claude", limit=1)

        assert len(sessions) == 1
        assert sessions[0].session_id == "sess-1"
    def _get_subagent_messages(session_id, agent_id, directory=None):
        if agent_id == "planner":
            raise RuntimeError("subagent transcript missing")
        return [
            FakeSessionMessage(
                type="assistant",
                uuid="sa1",
                session_id=session_id,
                message={"content": [{"text": f"{agent_id} done"}]},
            ),
        ]

    stub = SimpleNamespace(
        get_session_messages=lambda session_id, directory=None: [
            FakeSessionMessage(
                type="user",
                uuid="u1",
                session_id=session_id,
                message={"text": "Investigate a propagation bug"},
            ),
            FakeSessionMessage(
                type="assistant",
                uuid="a1",
                session_id=session_id,
                message={"content": [{"text": "Delegating to subagents."}]},
            ),
        ],
        get_session_info=lambda session_id, directory=None: {"summary": "Propagation session"},
        list_subagents=lambda session_id, directory=None: ["reviewer", "planner"],
        get_subagent_messages=_get_subagent_messages,
    )
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: stub,
    )

    trace = import_claude_session("sess-1")

    assert any(span.name == "reviewer" for span in trace.agent_spans)
    assert all(span.name != "planner" for span in trace.agent_spans)
    assert trace.metadata["claude.subagent_imported_count"] == 1
    assert trace.metadata["claude.subagent_import_skipped"] == [
        {
            "agent_id": "planner",
            "reason": "Claude SDK get_subagent_messages() failed: subagent transcript missing",
        }
    ]


def test_import_claude_session_enriches_spans_with_jsonl_timestamps(monkeypatch, tmp_path):
    """The importer must recover timestamps from the raw JSONL, since the
    Claude SDK strips them from SessionMessage. Without this enrichment,
    every span has duration_ms=0 and the diagnose report cannot surface
    real wait times (e.g. how long a Bash tool_use took to return)."""
    import json

    session_id = "sess-jsonl-1"
    projects_dir = tmp_path / ".claude" / "projects" / "-tmp-proj"
    projects_dir.mkdir(parents=True)
    jsonl_path = projects_dir / f"{session_id}.jsonl"

    t0 = "2026-04-21T08:00:00.000Z"
    t1 = "2026-04-21T08:00:05.000Z"  # assistant generates tool_use
    t2 = "2026-04-21T08:01:15.000Z"  # tool_result returns 70s later
    t3 = "2026-04-21T08:01:20.000Z"  # assistant final reply

    records = [
        {"uuid": "u1", "timestamp": t0, "type": "user",
         "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}},
        {"uuid": "a1", "timestamp": t1, "type": "assistant",
         "message": {"role": "assistant", "content": [
             {"type": "tool_use", "id": "tool-abc", "name": "Bash",
              "input": {"command": "slow-thing"}}
         ]}},
        {"uuid": "u2", "timestamp": t2, "type": "user",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "tool-abc", "content": "ok"}
         ]}},
        {"uuid": "a2", "timestamp": t3, "type": "assistant",
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": "done"}
         ]}},
    ]
    jsonl_path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))

    # Give the SDK stub the same uuids so timestamps can be matched back.
    session_messages = [
        FakeSessionMessage(type="user", uuid="u1", session_id=session_id,
                           message={"text": "hi"}),
        FakeSessionMessage(type="assistant", uuid="a1", session_id=session_id,
                           message={"content": [{"text": "calling bash"}]}),
        FakeSessionMessage(type="user", uuid="u2", session_id=session_id,
                           message={"content": [{"text": "ok"}]}),
        FakeSessionMessage(type="assistant", uuid="a2", session_id=session_id,
                           message={"content": [{"text": "done"}]}),
    ]
    stub = SimpleNamespace(
        get_session_messages=lambda sid, directory=None: session_messages,
        get_session_info=lambda sid, directory=None: FakeSessionInfo(
            session_id=sid, summary="slow bash session"),
    )
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: stub,
    )

    trace = import_claude_session(session_id)

    # Metadata advertises timestamps were recovered.
    assert trace.metadata.get("claude.timestamps_available") is True

    # Root span covers the full session window.
    root = next(s for s in trace.spans if s.span_type == SpanType.AGENT
                and s.parent_span_id is None)
    assert root.started_at == t0
    assert root.ended_at == t3
    assert root.duration_ms is not None and root.duration_ms > 70000

    # Assistant LLM spans are pinned to their observed timestamps.
    llm_spans = [s for s in trace.spans if s.span_type == SpanType.LLM_CALL]
    assert llm_spans
    assert any(s.started_at == t1 for s in llm_spans)
    assert any(s.started_at == t3 for s in llm_spans)

    # The tool_use -> tool_result pair becomes an explicit TOOL span
    # whose duration is the real wall-clock wait (70s).
    tool_spans = [s for s in trace.spans if s.span_type == SpanType.TOOL]
    assert len(tool_spans) == 1
    tool = tool_spans[0]
    assert tool.name == "tool:Bash"
    assert tool.started_at == t1
    assert tool.ended_at == t2
    assert tool.duration_ms is not None
    assert 69_500 <= tool.duration_ms <= 70_500
    assert tool.metadata["claude.tool_use_id"] == "tool-abc"
    assert tool.metadata["claude.tool_name"] == "Bash"
    assert (tool.input_data or {}).get("command") == "slow-thing"


def test_import_claude_session_falls_back_gracefully_without_jsonl(monkeypatch, tmp_path):
    """When the raw JSONL cannot be found, import must still succeed.
    All durations stay 0 but no exception is raised."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: _sdk_stub(include_subagents=False),
    )

    trace = import_claude_session("sess-1")

    assert "claude.timestamps_available" not in trace.metadata
    # No tool-wait spans synthesized because no JSONL was found.
    assert all(s.span_type != SpanType.TOOL for s in trace.spans)


def test_import_claude_session_enriches_spans_with_jsonl_timestamps(monkeypatch, tmp_path):
    """The importer must recover timestamps from the raw JSONL, since the
    Claude SDK strips them from SessionMessage. Without this enrichment,
    every span has duration_ms=0 and the diagnose report cannot surface
    real wait times (e.g. how long a Bash tool_use took to return)."""
    import json

    session_id = "sess-jsonl-1"
    projects_dir = tmp_path / ".claude" / "projects" / "-tmp-proj"
    projects_dir.mkdir(parents=True)
    jsonl_path = projects_dir / f"{session_id}.jsonl"

    t0 = "2026-04-21T08:00:00.000Z"
    t1 = "2026-04-21T08:00:05.000Z"  # assistant generates tool_use
    t2 = "2026-04-21T08:01:15.000Z"  # tool_result returns 70s later
    t3 = "2026-04-21T08:01:20.000Z"  # assistant final reply

    records = [
        {"uuid": "u1", "timestamp": t0, "type": "user",
         "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}},
        {"uuid": "a1", "timestamp": t1, "type": "assistant",
         "message": {"role": "assistant", "content": [
             {"type": "tool_use", "id": "tool-abc", "name": "Bash",
              "input": {"command": "slow-thing"}}
         ]}},
        {"uuid": "u2", "timestamp": t2, "type": "user",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "tool-abc", "content": "ok"}
         ]}},
        {"uuid": "a2", "timestamp": t3, "type": "assistant",
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": "done"}
         ]}},
    ]
    jsonl_path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))

    # Give the SDK stub the same uuids so timestamps can be matched back.
    session_messages = [
        FakeSessionMessage(type="user", uuid="u1", session_id=session_id,
                           message={"text": "hi"}),
        FakeSessionMessage(type="assistant", uuid="a1", session_id=session_id,
                           message={"content": [{"text": "calling bash"}]}),
        FakeSessionMessage(type="user", uuid="u2", session_id=session_id,
                           message={"content": [{"text": "ok"}]}),
        FakeSessionMessage(type="assistant", uuid="a2", session_id=session_id,
                           message={"content": [{"text": "done"}]}),
    ]
    stub = SimpleNamespace(
        get_session_messages=lambda sid, directory=None: session_messages,
        get_session_info=lambda sid, directory=None: FakeSessionInfo(
            session_id=sid, summary="slow bash session"),
    )
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: stub,
    )

    trace = import_claude_session(session_id)

    # Metadata advertises timestamps were recovered.
    assert trace.metadata.get("claude.timestamps_available") is True

    # Root span covers the full session window.
    root = next(s for s in trace.spans if s.span_type == SpanType.AGENT
                and s.parent_span_id is None)
    assert root.started_at == t0
    assert root.ended_at == t3
    assert root.duration_ms is not None and root.duration_ms > 70000

    # Assistant LLM spans are pinned to their observed timestamps.
    llm_spans = [s for s in trace.spans if s.span_type == SpanType.LLM_CALL]
    assert llm_spans
    assert any(s.started_at == t1 for s in llm_spans)
    assert any(s.started_at == t3 for s in llm_spans)

    # The tool_use -> tool_result pair becomes an explicit TOOL span
    # whose duration is the real wall-clock wait (70s).
    tool_spans = [s for s in trace.spans if s.span_type == SpanType.TOOL]
    assert len(tool_spans) == 1
    tool = tool_spans[0]
    assert tool.name == "tool:Bash"
    assert tool.started_at == t1
    assert tool.ended_at == t2
    assert tool.duration_ms is not None
    assert 69_500 <= tool.duration_ms <= 70_500
    assert tool.metadata["claude.tool_use_id"] == "tool-abc"
    assert tool.metadata["claude.tool_name"] == "Bash"
    assert (tool.input_data or {}).get("command") == "slow-thing"


def test_import_claude_session_falls_back_gracefully_without_jsonl(monkeypatch, tmp_path):
    """When the raw JSONL cannot be found, import must still succeed.
    All durations stay 0 but no exception is raised."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: _sdk_stub(include_subagents=False),
    )

    trace = import_claude_session("sess-1")

    assert "claude.timestamps_available" not in trace.metadata
    # No tool-wait spans synthesized because no JSONL was found.
    assert all(s.span_type != SpanType.TOOL for s in trace.spans)
