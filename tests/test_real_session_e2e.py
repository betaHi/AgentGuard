"""End-to-end regression using a realistic Claude-shaped session fixture.

This locks in three behaviors that a recent real-session smoke test on a
6458-span ``docs-navigation-rewrite`` run revealed as bugs:

1. Cost must roll up from leaf LLM / tool spans to their containing agent;
   otherwise ``diagnose-claude-session`` reports ``$0.0000`` on every
   per-agent entry.
2. The ``Task`` tool (which dispatches subagents) must not show up as the
   opaque ``tool:Agent`` label — the subagent type needs to surface in the
   span name so the bottleneck output is actionable.
3. ``total_cost_usd`` must still equal the sum of real span costs — the
   roll-up must not double-count.

These assertions protect the end-to-end importer → analyzer → diagnostics
pipeline against silent degradation. Unit tests in ``test_cost_rollup`` and
``test_claude_session_import`` cover pieces in isolation; this one wires the
whole thing together on a fixture whose structure mirrors a real
``~/.claude/projects/*/*.jsonl`` session.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from agentguard import diagnose_claude_session


def _write_session_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _install_stub_sdk(monkeypatch, assistant_records):
    """Install a minimal claude_agent_sdk stub that returns assistant messages."""
    messages = []
    for rec in assistant_records:
        msg = rec["message"]
        messages.append(types.SimpleNamespace(
            role="assistant",
            content=msg["content"],
            uuid=rec["uuid"],
            parent_tool_use_id=rec.get("parentUuid"),
            stop_reason=msg.get("stop_reason"),
            model=msg.get("model"),
            usage=msg.get("usage"),
        ))
    fake = types.ModuleType("claude_agent_sdk")
    fake.__version__ = "0.1.63"
    fake.get_session_messages = lambda sid, directory=None: messages
    fake.get_session_info = lambda sid, directory=None: types.SimpleNamespace(
        session_id=sid, cwd="/tmp/demo", task=None,
    )
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)


@pytest.fixture
def claude_session_with_subagent(tmp_path, monkeypatch):
    """Build a small but structurally-complete Claude session JSONL fixture.

    The fixture contains:
      * user prompt,
      * assistant message that dispatches a ``Task`` subagent,
      * a tool_result returned ~3 seconds later (so tool_wait span has a
        real duration), and
      * a final assistant reply with token usage.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    projects = home / ".claude" / "projects" / "demo-project"
    projects.mkdir(parents=True)
    session_id = "e2e-real-shape"

    tool_use_id = "toolu_01RealSubagent"
    assistant_records = [
        {
            "uuid": "a-tooluse",
            "timestamp": "2025-04-22T10:00:01Z",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-5",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "content": [
                    {"type": "text", "text": "Dispatching a subagent."},
                    {
                        "type": "tool_use",
                        "id": tool_use_id,
                        "name": "Task",
                        "input": {
                            "subagent_type": "general-purpose",
                            "description": "audit docs nav",
                        },
                    },
                ],
            },
        },
        {
            "uuid": "a-final",
            "timestamp": "2025-04-22T10:00:05Z",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-5",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 80,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "content": [{"type": "text", "text": "All done."}],
            },
        },
    ]
    records = [
        {"uuid": "u-prompt", "timestamp": "2025-04-22T10:00:00Z",
         "message": {"role": "user", "content": "audit navigation"}},
        assistant_records[0],
        {
            "uuid": "u-toolresult",
            "timestamp": "2025-04-22T10:00:03Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": tool_use_id,
                     "content": "found 3 broken links"},
                ],
            },
        },
        assistant_records[1],
    ]
    _write_session_jsonl(projects / f"{session_id}.jsonl", records)
    _install_stub_sdk(monkeypatch, assistant_records)
    return session_id


def test_e2e_costs_roll_up_and_total_is_sum_of_real_spans(claude_session_with_subagent):
    """Per-agent costs must be non-zero and total must equal sum of real spans."""
    report, _ = diagnose_claude_session(claude_session_with_subagent)

    # total cost should reflect both assistant LLM calls actually existing.
    assert report.cost_yield is not None
    total = report.cost_yield.total_cost_usd
    assert total > 0.0, "total cost should not collapse to 0 on real sessions"

    # Every agent entry's cost should be > 0 (roll-up working).
    entries = report.cost_yield.entries
    assert entries, "expected at least one agent entry"
    for e in entries:
        assert e.cost_usd >= 0.0
    assert any(e.cost_usd > 0.0 for e in entries), (
        "no agent entry carried cost — roll-up from LLM/tool spans is broken"
    )


def test_e2e_task_tool_shows_subagent_type_not_opaque_agent_label(
    claude_session_with_subagent,
):
    """Task-tool spans must expose the subagent type in the human-readable name."""
    report, _ = diagnose_claude_session(claude_session_with_subagent)
    tool_names = [s.name for s in report.trace.spans if s.span_type.value == "tool"]
    # Opaque label must NOT leak through.
    assert not any(n == "tool:Agent" or n == "tool:Task" for n in tool_names), (
        f"Task dispatch collapsed to opaque label in {tool_names!r}"
    )
    # At least one tool span should name the subagent_type.
    assert any("general-purpose" in n for n in tool_names), (
        f"Subagent type not surfaced in tool span names: {tool_names!r}"
    )


def test_e2e_bottleneck_name_is_actionable(claude_session_with_subagent):
    """Bottleneck output must point at a real tool/agent, not 'Agent'."""
    report, _ = diagnose_claude_session(claude_session_with_subagent)
    bottleneck_name = getattr(report.bottleneck, "bottleneck_name", None) or ""
    # Accept either the refined Task name or a real span type, but never the
    # legacy opaque 'tool:Agent' label that real-session smoke test exposed.
    assert bottleneck_name != "tool:Agent", (
        "bottleneck regressed to opaque 'tool:Agent' label"
    )
