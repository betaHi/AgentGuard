"""Q4 — deliverable extraction from the final assistant payload."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from agentguard.runtime.claude import session_import
from agentguard.runtime.claude.session_import import _extract_deliverable_refs


def test_extract_file_paths():
    refs = _extract_deliverable_refs([
        {"type": "text", "text": "Wrote `src/app/main.py` and updated docs/README.md"},
    ])
    assert "src/app/main.py" in refs
    assert "docs/README.md" in refs


def test_extract_urls():
    refs = _extract_deliverable_refs([
        {"type": "text", "text": "See https://example.com/pr/42 for the change"},
    ])
    assert any(r.startswith("https://example.com") for r in refs)


def test_extract_code_fences():
    refs = _extract_deliverable_refs([
        {"type": "text", "text": "```python\nprint(1)\n```\n```bash\nls\n```"},
    ])
    assert any(r.startswith("<code-block") for r in refs)


def test_no_deliverables_in_plain_chatter():
    refs = _extract_deliverable_refs([
        {"type": "text", "text": "Yes, I agree with that plan."},
    ])
    assert refs == set()


def test_extract_from_tool_use_block_inputs():
    refs = _extract_deliverable_refs([
        {"type": "tool_use", "name": "write", "input": {"path": "out/result.json"}},
    ])
    assert "out/result.json" in refs


def _install_stub_sdk(monkeypatch, records):
    assistants = []
    for rec in records:
        msg = rec["message"]
        if msg.get("role") == "assistant":
            assistants.append(types.SimpleNamespace(
                type="assistant",
                role="assistant",
                # Real SDK exposes the Anthropic message shape under ``.message``.
                message=types.SimpleNamespace(
                    role="assistant",
                    content=msg["content"],
                    stop_reason=msg.get("stop_reason"),
                    model=msg.get("model"),
                    usage=msg.get("usage"),
                ),
                content=msg["content"],
                uuid=rec["uuid"],
                parent_tool_use_id=None,
                stop_reason=msg.get("stop_reason"),
                model=msg.get("model"),
                usage=msg.get("usage"),
            ))
    fake = types.ModuleType("claude_agent_sdk")
    fake.__version__ = "0.5.0"
    fake.get_session_messages = lambda sid, directory=None: assistants
    fake.get_session_info = lambda sid, directory=None: types.SimpleNamespace(
        session_id=sid, cwd=None, task=None,
    )
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)


def test_deliverables_boost_completion_signal(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    projects = home / ".claude" / "projects" / "proj"
    projects.mkdir(parents=True)

    session_id = "deliverable-test"
    records = [
        {"uuid": "u1", "timestamp": "2024-01-01T00:00:00Z",
         "message": {"role": "user", "content": "hi"}},
        {"uuid": "a1", "timestamp": "2024-01-01T00:00:01Z",
         "message": {
             "role": "assistant",
             "model": "claude-opus-4.7",
             "stop_reason": "end_turn",
             "content": [{
                 "type": "text",
                 "text": (
                     "I wrote `src/app/main.py`, updated `docs/README.md`, "
                     "and opened https://github.com/x/y/pull/1."
                 ),
             }],
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

    trace = session_import.import_claude_session(session_id)

    # With deliverables present, the clean-end signal saturates at 1.0.
    assert trace.metadata["claude.completion_signal"] == pytest.approx(1.0)
    assert trace.metadata["claude.deliverables_count"] >= 3
    assert "src/app/main.py" in trace.metadata["claude.deliverables"]
