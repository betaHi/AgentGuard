"""JSONL → trace fidelity regression tests.

These tests protect against silent data loss during Claude session import.
The Claude SDK has historically dropped assistant records the raw JSONL
retains (thinking blocks, tool-result carriers, compaction stubs). It also
evolves its ``usage`` schema across releases. These tests assert that the
importer's per-session token and tool totals match the JSONL ground truth
down to the last token — any drift here silently distorts cost-yield and
bottleneck analysis.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentguard.core.trace import SpanType
from agentguard.runtime.claude.session_import import import_claude_session


SESSION_ID = "sess-fidelity"


def _msg(
    uuid: str,
    role: str,
    *,
    text: str = "",
    usage: dict[str, Any] | None = None,
    model: str | None = None,
    parent_tool_use_id: str | None = None,
    content: list[dict] | None = None,
) -> dict:
    """Build a single raw JSONL record shaped like Claude's transcript."""
    message: dict[str, Any] = {"role": role}
    if usage is not None:
        message["usage"] = usage
    if model is not None:
        message["model"] = model
    if content is not None:
        message["content"] = content
    elif text:
        message["content"] = [{"type": "text", "text": text}]
    record: dict[str, Any] = {
        "uuid": uuid,
        "type": role,
        "timestamp": "2026-04-20T12:00:00Z",
        "message": message,
    }
    if parent_tool_use_id:
        record["parent_tool_use_id"] = parent_tool_use_id
    return record


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


@pytest.fixture
def fidelity_session(tmp_path, monkeypatch):
    """Build a miniature project/session layout that mirrors the real tree.

    Main session has three assistant records; the SDK (stub) returns only one
    of them. Subagent JSONL has two assistant records and two tool_use /
    tool_result pairs. If the importer is correct, the trace must reflect
    every usage-bearing record from both files.
    """
    projects = tmp_path / ".claude" / "projects"
    project_dir = projects / "proj"
    main_path = project_dir / f"{SESSION_ID}.jsonl"
    subagent_dir = project_dir / SESSION_ID / "subagents"
    subagent_path = subagent_dir / "agent-reviewer.jsonl"

    main_records = [
        _msg("u1", "user", text="Refactor the auth flow"),
        _msg(
            "a1",
            "assistant",
            text="Planning",
            model="claude-opus-4.7",
            usage={
                "input_tokens": 1_000,
                "output_tokens": 200,
                "cache_read_input_tokens": 5_000,
                "cache_creation_input_tokens": 0,
            },
        ),
        # SDK drops this "thinking" record; JSONL still has the usage.
        _msg(
            "a2",
            "assistant",
            text="Thinking",
            model="claude-opus-4.7",
            usage={
                "input_tokens": 3_000,
                "output_tokens": 50,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        ),
        # Tool use inside assistant message, triggers tool_wait span.
        _msg(
            "a3",
            "assistant",
            model="claude-opus-4.7",
            usage={"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            content=[
                {
                    "type": "tool_use",
                    "id": "tool-main",
                    "name": "Bash",
                    "input": {"command": "ls"},
                }
            ],
        ),
        # Tool result delivered as a user record per Claude JSONL schema.
        {
            "uuid": "tr-main",
            "type": "user",
            "timestamp": "2026-04-20T12:00:05Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-main",
                        "content": "ok",
                    }
                ],
            },
        },
    ]
    subagent_records = [
        _msg(
            "sa1",
            "assistant",
            text="Reviewer-1",
            model="gpt-5",
            usage={
                "input_tokens": 10_000,
                "output_tokens": 400,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        ),
        _msg(
            "sa2",
            "assistant",
            model="gpt-5",
            usage={
                "input_tokens": 15_000,
                "output_tokens": 500,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            content=[
                {
                    "type": "tool_use",
                    "id": "tool-sub",
                    "name": "Grep",
                    "input": {"pattern": "TODO"},
                }
            ],
        ),
        {
            "uuid": "tr-sub",
            "type": "user",
            "timestamp": "2026-04-20T12:00:07Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-sub",
                        "content": "hit",
                    }
                ],
            },
        },
    ]
    _write_jsonl(main_path, main_records)
    _write_jsonl(subagent_path, subagent_records)

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))

    # SDK stub returns only ONE assistant message from main + only reviewer.
    def _session_messages(session_id, directory=None):
        return [
            SimpleNamespace(type="user", uuid="u1", session_id=session_id, message={"text": "Refactor the auth flow"}, parent_tool_use_id=None),
            SimpleNamespace(type="assistant", uuid="a1", session_id=session_id, message={"content": [{"text": "Planning"}]}, parent_tool_use_id=None),
        ]

    def _subagent_messages(session_id, agent_id, directory=None):
        return [
            SimpleNamespace(type="assistant", uuid="sa1", session_id=session_id, message={"content": [{"text": "Reviewer-1"}]}, parent_tool_use_id=None),
        ]

    stub = SimpleNamespace(
        get_session_messages=_session_messages,
        get_session_info=lambda session_id, directory=None: SimpleNamespace(summary="Fidelity test", custom_title="fidelity"),
        list_subagents=lambda session_id, directory=None: ["reviewer"],
        get_subagent_messages=_subagent_messages,
    )
    monkeypatch.setattr(
        "agentguard.runtime.claude.session_import._load_sdk_module",
        lambda: stub,
    )

    return {"main_path": main_path, "subagent_path": subagent_path}


def _jsonl_usage_totals(*paths: Path) -> dict[str, int]:
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "calls": 0}
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            usage = (record.get("message") or {}).get("usage")
            if not usage:
                continue
            totals["input"] += usage.get("input_tokens", 0) or 0
            totals["output"] += usage.get("output_tokens", 0) or 0
            totals["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
            totals["cache_creation"] += usage.get("cache_creation_input_tokens", 0) or 0
            totals["calls"] += 1
    return totals


def _trace_usage_totals(trace) -> dict[str, int]:
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "calls": 0}
    for span in trace.spans:
        if span.span_type != SpanType.LLM_CALL:
            continue
        md = span.metadata or {}
        totals["input"] += int(md.get("claude.usage.input_tokens", 0) or 0)
        totals["output"] += int(md.get("claude.usage.output_tokens", 0) or 0)
        totals["cache_read"] += int(md.get("claude.usage.cache_read_input_tokens", 0) or 0)
        totals["cache_creation"] += int(md.get("claude.usage.cache_creation_input_tokens", 0) or 0)
        totals["calls"] += 1
    return totals


def test_token_totals_match_jsonl_ground_truth(fidelity_session):
    """Every usage-bearing JSONL record must appear in the trace totals.

    Regression target: the SDK silently drops assistant records that carry
    usage metadata; without the reconcile pass the trace under-counted
    tokens by 55%+ on real sessions.
    """
    expected = _jsonl_usage_totals(fidelity_session["main_path"], fidelity_session["subagent_path"])

    trace = import_claude_session(SESSION_ID)

    actual = _trace_usage_totals(trace)
    assert actual["input"] == expected["input"]
    assert actual["output"] == expected["output"]
    assert actual["cache_read"] == expected["cache_read"]
    assert actual["cache_creation"] == expected["cache_creation"]
    # calls: the stub returned 2 assistant messages; JSONL has 5 usage-bearing
    # records. Reconcile must backfill the remaining 3.
    assert actual["calls"] == expected["calls"]


def test_tool_waits_include_subagent_pairs(fidelity_session):
    """Subagent tool_use/tool_result pairs must be imported as tool spans.

    Regression target: bottleneck / critical-path analysis used to miss
    every subagent tool wait because only the main JSONL was scanned.
    """
    trace = import_claude_session(SESSION_ID)

    tool_waits = [
        s for s in trace.spans
        if s.span_type == SpanType.TOOL
        and (s.metadata or {}).get("claude.scope") == "tool_wait"
    ]
    tool_ids = {(s.metadata or {}).get("claude.tool_use_id") for s in tool_waits}
    assert "tool-main" in tool_ids, "missing main-session tool_wait"
    assert "tool-sub" in tool_ids, "missing subagent tool_wait (regression)"


def test_reconciled_spans_are_marked_for_provenance(fidelity_session):
    """Reconciled spans must be distinguishable from SDK-returned spans."""
    trace = import_claude_session(SESSION_ID)

    reconciled = [
        s for s in trace.spans
        if (s.metadata or {}).get("claude.source") == "jsonl_reconcile"
    ]
    # JSONL has 5 usage records; SDK returned 2 → 3 spans must be reconciled.
    assert len(reconciled) == 3


def test_unknown_model_uses_fallback_pricing_and_flags_span(fidelity_session):
    """Unknown model ids must still be priced but flagged as fallback.

    Regression target: silently returning ``None`` for unknown models
    under-counted cost; silently defaulting to Opus over-counted it.
    """
    # Rewrite one span to use an unknown model id, then re-import.
    main_path = fidelity_session["main_path"]
    raw = main_path.read_text(encoding="utf-8").splitlines()
    patched = []
    for line in raw:
        rec = json.loads(line)
        msg = rec.get("message") or {}
        if msg.get("model") == "claude-opus-4.7":
            msg["model"] = "mystery-model-7"
        patched.append(json.dumps(rec))
    main_path.write_text("\n".join(patched), encoding="utf-8")

    trace = import_claude_session(SESSION_ID)

    flagged = [
        s for s in trace.spans
        if (s.metadata or {}).get("claude.cost_pricing") == "fallback"
        and s.estimated_cost_usd is not None
    ]
    assert flagged, "unknown model must be priced with a fallback badge"
