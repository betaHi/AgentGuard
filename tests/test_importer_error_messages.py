"""P2.10 — actionable error messages across the importer surface.

Every ClaudeSessionImportError must tell the user what was attempted and
what to try next. A bare ``RuntimeError("non-list result")`` is worse
than useless for anyone who didn't write the code — the message must
close the loop.
"""

from __future__ import annotations

import sys
import types

import pytest

from agentguard.runtime.claude.session_import import (
    ClaudeSessionImportError,
    _coerce_list,
    _sdk_helper_missing_message,
    import_claude_session,
    list_claude_sessions,
)


def test_sdk_helper_missing_message_includes_version_range():
    msg = _sdk_helper_missing_message("get_session_messages")
    assert "get_session_messages" in msg
    assert "pip install" in msg
    assert "claude-agent-sdk>=" in msg
    # Three-state explanation so the user can self-diagnose.
    assert "older" in msg.lower() or "fork" in msg.lower()


def test_list_sessions_missing_helper_gives_install_command(monkeypatch):
    fake = types.ModuleType("claude_agent_sdk")
    fake.__version__ = "0.1.65"
    # no list_sessions on purpose
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    with pytest.raises(ClaudeSessionImportError) as excinfo:
        list_claude_sessions()
    msg = str(excinfo.value)
    assert "list_sessions" in msg
    assert "pip install" in msg


def test_import_missing_helper_gives_install_command(monkeypatch):
    fake = types.ModuleType("claude_agent_sdk")
    fake.__version__ = "0.1.65"
    # no get_session_messages on purpose
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    with pytest.raises(ClaudeSessionImportError) as excinfo:
        import_claude_session("abc")
    msg = str(excinfo.value)
    assert "get_session_messages" in msg
    assert "pip install" in msg


def test_sdk_helper_failure_message_suggests_projects_dir_flag(monkeypatch):
    def boom(session_id, directory=None):
        raise RuntimeError("disk on fire")

    fake = types.ModuleType("claude_agent_sdk")
    fake.__version__ = "0.1.65"
    fake.get_session_messages = boom
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    with pytest.raises(ClaudeSessionImportError) as excinfo:
        import_claude_session("abc", directory="/tmp/p")
    msg = str(excinfo.value)
    assert "disk on fire" in msg
    assert "--claude-projects-dir" in msg
    assert "/tmp/p" in msg  # directory must be surfaced


def test_coerce_list_gives_type_and_sdk_hint_on_wrong_shape():
    with pytest.raises(ClaudeSessionImportError) as excinfo:
        _coerce_list({"not": "a list"}, "list_sessions")
    msg = str(excinfo.value)
    assert "list_sessions" in msg
    assert "dict" in msg
    assert "SDK version mismatch" in msg
