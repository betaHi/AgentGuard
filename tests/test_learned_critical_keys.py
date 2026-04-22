"""Q2 — critical keys must be learned from the trace, not a hardcoded list."""

from __future__ import annotations

from datetime import datetime, timezone

from agentguard.analysis import (
    _infer_critical_keys,
    _learn_critical_keys_from_trace,
    analyze_context_flow,
)
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _span(sid, name, parent, inp, out, ts_offset: int = 0, span_type=SpanType.AGENT):
    start = datetime(2024, 1, 1, 0, 0, ts_offset, tzinfo=timezone.utc).isoformat()
    end = datetime(2024, 1, 1, 0, 0, ts_offset + 1, tzinfo=timezone.utc).isoformat()
    return Span(
        span_id=sid, trace_id="t", name=name,
        parent_span_id=parent,
        span_type=span_type, status=SpanStatus.COMPLETED,
        started_at=start, ended_at=end,
        input_data=inp, output_data=out,
    )


def _trace_with_domain_keys() -> ExecutionTrace:
    """A trace where ``file_list`` is produced by agent1 and consumed by 2+ later agents."""
    trace = ExecutionTrace(trace_id="t", task="docs", trigger="unit-test")
    trace.add_span(_span("root", "root", None, None, None, 0))
    # agent1 produces a domain-specific "file_list" output
    trace.add_span(_span(
        "a1", "indexer", "root",
        {"query": "docs"},
        {"file_list": ["a.md", "b.md"], "nav_tree": {"root": "a"}},
        2,
    ))
    # agent2 consumes file_list
    trace.add_span(_span(
        "a2", "writer", "root",
        {"file_list": ["a.md", "b.md"]},
        {"draft": "..."},
        4,
    ))
    # agent3 consumes file_list via text reference
    trace.add_span(_span(
        "a3", "reviewer", "root",
        {"context": "review using file_list from indexer"},
        {"verdict": "ok"},
        6,
    ))
    # agent4 consumes nav_tree
    trace.add_span(_span(
        "a4", "publisher", "root",
        {"nav_tree": {"root": "a"}},
        {"published": True},
        8,
    ))
    return trace


def test_learned_keys_pick_up_domain_specific_critical_fields():
    trace = _trace_with_domain_keys()
    learned = _learn_critical_keys_from_trace(trace)
    assert "file_list" in learned, f"expected file_list, got {learned}"


def test_learned_keys_ignore_one_off_echoes():
    trace = ExecutionTrace(trace_id="t", task="x", trigger="unit-test")
    trace.add_span(_span("root", "root", None, None, None, 0))
    trace.add_span(_span("a1", "a1", "root", {}, {"tmp_flag": 1}, 2))
    # Only one consumer — must NOT be promoted.
    trace.add_span(_span("a2", "a2", "root", {"tmp_flag": 1}, {}, 4))
    learned = _learn_critical_keys_from_trace(trace)
    assert "tmp_flag" not in learned


def test_infer_critical_keys_still_returns_heuristic_keys_without_learning():
    # Direct call without analyze_context_flow running first — should fall
    # back to the English keyword heuristic.
    keys = _infer_critical_keys({"query": "x", "irrelevant_blob": 1})
    assert "query" in keys
    assert "irrelevant_blob" not in keys


def test_analyze_context_flow_records_learned_keys_on_trace():
    trace = _trace_with_domain_keys()
    analyze_context_flow(trace)
    assert "file_list" in trace.metadata.get("context.learned_critical_keys", [])
