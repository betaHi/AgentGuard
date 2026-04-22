"""Actionable error messages for common import failures."""

from __future__ import annotations

import sys
import types

import pytest

from agentguard.runtime.claude.session_import import (
    ClaudeSessionImportError,
    _session_not_found_message,
    import_claude_session,
)


def test_not_found_message_lists_checked_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    msg = _session_not_found_message("abc-123", directory=None)
    assert "abc-123" in msg
    assert ".claude/projects" in msg
    assert "list-claude-sessions" in msg
    assert "--directory" in msg
    assert "CLAUDE_CONFIG_DIR" in msg


def test_not_found_message_surfaces_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/opt/claude")
    msg = _session_not_found_message("abc", directory="/tmp/proj")
    assert "/opt/claude" in msg
    assert "/tmp/proj" in msg


def test_import_raises_actionable_error_when_session_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

    fake = types.ModuleType("claude_agent_sdk")
    fake.__version__ = "0.5.0"
    fake.get_session_messages = lambda sid, directory=None: []
    fake.get_session_info = lambda sid, directory=None: None
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    with pytest.raises(ClaudeSessionImportError) as excinfo:
        import_claude_session("abc-123")
    msg = str(excinfo.value)
    assert "abc-123" in msg
    assert "Fixes to try" in msg
    assert "list-claude-sessions" in msg
