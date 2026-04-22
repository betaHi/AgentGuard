"""Tests for the single-call publishable entry point ``diagnose_claude_session``."""

from __future__ import annotations

import json
import sys
import types

import pytest

import agentguard
from agentguard import diagnose_claude_session
from agentguard.diagnostics import DiagnosticReport


def _install_stub_sdk(monkeypatch, records):
    assistant_messages = []
    for rec in records:
        msg = rec["message"]
        if msg.get("role") == "assistant":
            assistant_messages.append(types.SimpleNamespace(
                role="assistant",
                content=msg["content"],
                uuid=rec["uuid"],
                parent_tool_use_id=None,
                stop_reason=msg.get("stop_reason"),
                model=msg.get("model"),
                usage=msg.get("usage"),
            ))
    fake = types.ModuleType("claude_agent_sdk")
    fake.get_session_messages = lambda sid, directory=None: assistant_messages
    fake.get_session_info = lambda sid, directory=None: types.SimpleNamespace(
        session_id=sid, cwd=None, task=None,
    )
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)


@pytest.fixture
def fake_session(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    projects = home / ".claude" / "projects" / "proj"
    projects.mkdir(parents=True)
    session_id = "entry-point-test"
    records = [
        {"uuid": "u1", "timestamp": "2024-01-01T00:00:00Z",
         "message": {"role": "user", "content": "hi"}},
        {"uuid": "a1", "timestamp": "2024-01-01T00:00:01Z",
         "message": {
             "role": "assistant",
             "model": "claude-opus-4.7",
             "stop_reason": "end_turn",
             "content": [{"type": "text", "text": "done"}],
             "usage": {
                 "input_tokens": 10, "output_tokens": 5,
                 "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
             },
         }},
    ]
    (projects / f"{session_id}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8",
    )
    _install_stub_sdk(monkeypatch, records)
    return session_id


def test_public_api_has_narrow_surface():
    """__all__ must stay small — this is the product boundary."""
    assert "diagnose_claude_session" in agentguard.__all__
    # No legacy capture API leaks into __all__
    for legacy in ("record_agent", "AgentTrace", "TraceThread", "record_handoff"):
        assert legacy not in agentguard.__all__, legacy
    assert len(agentguard.__all__) < 25, (
        f"Public surface grew to {len(agentguard.__all__)} names — keep it narrow"
    )


def test_diagnose_claude_session_returns_report_and_no_html(fake_session):
    report, html_path = diagnose_claude_session(fake_session)
    assert isinstance(report, DiagnosticReport)
    assert html_path is None
    assert report.trace.metadata.get("claude.stop_reason") == "end_turn"


def test_diagnose_claude_session_writes_html(fake_session, tmp_path):
    out = tmp_path / "report.html"
    report, html_path = diagnose_claude_session(
        fake_session, html_out=str(out),
    )
    assert html_path == str(out)
    assert out.exists() and out.stat().st_size > 0
    assert isinstance(report, DiagnosticReport)
