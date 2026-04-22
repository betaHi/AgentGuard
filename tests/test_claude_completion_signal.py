"""Q4 — completion signal extraction from Claude stop_reason."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from agentguard.runtime.claude import session_import
from agentguard.web.viewer import trace_to_html_string


def _msg(role: str, uuid: str, *, stop_reason: str | None = None, text: str = "ok",
         usage: dict[str, int] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": role,
        "model": "claude-opus-4.7",
        "content": [{"type": "text", "text": text}],
    }
    if stop_reason is not None:
        message["stop_reason"] = stop_reason
    if usage is not None:
        message["usage"] = usage
    return {
        "uuid": uuid,
        "timestamp": "2024-01-01T00:00:00.000Z",
        "message": message,
    }


def _write(tmp_path: Path, session_id: str, records: list[dict]) -> Path:
    projects = tmp_path / ".claude" / "projects" / "proj"
    projects.mkdir(parents=True)
    jsonl = projects / f"{session_id}.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return projects.parent.parent  # ~/.claude


def _install_stub_sdk(monkeypatch, session_id: str, records: list[dict]) -> None:
    """Install a fake claude_agent_sdk module so import_claude_session runs."""
    assistant_messages = []
    for rec in records:
        msg = rec["message"]
        if msg.get("role") == "assistant":
            obj = types.SimpleNamespace(
                role="assistant",
                content=msg["content"],
                uuid=rec["uuid"],
                parent_tool_use_id=None,
                stop_reason=msg.get("stop_reason"),
                model=msg.get("model"),
                usage=msg.get("usage"),
            )
            assistant_messages.append(obj)

    fake_sdk = types.ModuleType("claude_agent_sdk")

    def get_session_messages(sid, directory=None):  # noqa: ARG001
        return assistant_messages

    def get_session_info(sid, directory=None):  # noqa: ARG001
        return types.SimpleNamespace(session_id=sid, cwd=None, task=None)

    fake_sdk.get_session_messages = get_session_messages
    fake_sdk.get_session_info = get_session_info
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)


@pytest.fixture
def claude_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    return home


def _run(monkeypatch, claude_home, stop_reason):
    session_id = "q4-test"
    records = [
        {"uuid": "u1", "timestamp": "2024-01-01T00:00:00Z",
         "message": {"role": "user", "content": "hi"}},
        _msg("assistant", "a1", stop_reason=stop_reason,
             usage={"input_tokens": 10, "output_tokens": 5,
                    "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
    ]
    projects = claude_home / ".claude" / "projects" / "proj"
    projects.mkdir(parents=True)
    jsonl_path = projects / f"{session_id}.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    _install_stub_sdk(monkeypatch, session_id, records)
    return session_import.import_claude_session(session_id)


def test_end_turn_marks_clean_completion(monkeypatch, claude_home):
    trace = _run(monkeypatch, claude_home, "end_turn")
    assert trace.metadata["claude.stop_reason"] == "end_turn"
    # With no deliverables in the final payload the clean-end signal is
    # discounted so silent "nice reply / nothing shipped" doesn't look
    # perfect. With deliverables the test below verifies the 1.0 path.
    assert trace.metadata["claude.completion_signal"] == pytest.approx(0.7)
    root = trace.spans[0]
    assert root.metadata["claude.quality"] == pytest.approx(0.7)


def test_max_tokens_drags_completion_signal_down(monkeypatch, claude_home):
    trace = _run(monkeypatch, claude_home, "max_tokens")
    assert trace.metadata["claude.stop_reason"] == "max_tokens"
    # 0.35 base stop-reason × 0.7 no-deliverable penalty ≈ 0.245
    assert trace.metadata["claude.completion_signal"] == pytest.approx(0.245)
    root = trace.spans[0]
    assert root.metadata["claude.quality"] == pytest.approx(0.245)


def test_completion_badge_rendered_in_header(monkeypatch, claude_home):
    trace = _run(monkeypatch, claude_home, "max_tokens")
    html = trace_to_html_string(trace)
    assert "Ended: max tokens" in html
    # max_tokens should render as the "bad" severity class
    assert 'class="bad">Ended: max tokens' in html


def test_unknown_stop_reason_still_exposed_without_signal(monkeypatch, claude_home):
    trace = _run(monkeypatch, claude_home, "unexpected_future_reason")
    assert trace.metadata["claude.stop_reason"] == "unexpected_future_reason"
    # No numeric signal produced, so it must not fake a quality score.
    assert "claude.completion_signal" not in trace.metadata
    assert "claude.quality" not in trace.spans[0].metadata
