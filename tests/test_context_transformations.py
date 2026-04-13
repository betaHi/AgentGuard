"""Tests for Q2 context transformation tracking.

Detects semantic changes during handoffs: summarization, filtering,
type changes, key renames — not just key presence/absence.
"""

from agentguard.builder import TraceBuilder
from agentguard.analysis import analyze_context_flow


def _summarization_trace():
    """Agent A sends long text, Agent B receives summary."""
    return (TraceBuilder("summarization")
        .agent("coordinator", duration_ms=3000)
            .agent("researcher", duration_ms=1000,
                   output_data={"report": "x" * 500, "score": 0.9})
            .end()
            .agent("writer", duration_ms=1000,
                   input_data={"report": "x" * 100, "score": 0.9})
            .end()
        .end().build())


def _filtering_trace():
    """Agent A sends list of 100, Agent B receives filtered 10."""
    return (TraceBuilder("filtering")
        .agent("coordinator", duration_ms=3000)
            .agent("collector", duration_ms=1000,
                   output_data={"items": list(range(100)), "meta": "ok"})
            .end()
            .agent("ranker", duration_ms=1000,
                   input_data={"items": list(range(10)), "meta": "ok"})
            .end()
        .end().build())


def _rename_trace():
    """Key renamed between agents."""
    return (TraceBuilder("rename")
        .agent("coordinator", duration_ms=3000)
            .agent("agent_a", duration_ms=1000,
                   output_data={"user_name": "Alice", "age": 30})
            .end()
            .agent("agent_b", duration_ms=1000,
                   input_data={"name": "Alice", "age": 30})
            .end()
        .end().build())


def _type_change_trace():
    """Value type changes between agents."""
    return (TraceBuilder("type change")
        .agent("coordinator", duration_ms=3000)
            .agent("parser", duration_ms=1000,
                   output_data={"count": "42"})
            .end()
            .agent("calculator", duration_ms=1000,
                   input_data={"count": 42})
            .end()
        .end().build())


def _no_transform_trace():
    """Perfect handoff — no transformations."""
    return (TraceBuilder("clean")
        .agent("coordinator", duration_ms=3000)
            .agent("a", duration_ms=1000,
                   output_data={"x": 1, "y": 2})
            .end()
            .agent("b", duration_ms=1000,
                   input_data={"x": 1, "y": 2})
            .end()
        .end().build())


class TestContextTransformations:
    def test_summarization_detected(self):
        ctx = analyze_context_flow(_summarization_trace())
        transforms = ctx.points[0].transformations if ctx.points else []
        types = [t["type"] for t in transforms]
        assert "summarization" in types or "compression" in types

    def test_filtering_detected(self):
        ctx = analyze_context_flow(_filtering_trace())
        transforms = ctx.points[0].transformations if ctx.points else []
        types = [t["type"] for t in transforms]
        assert "filtering" in types

    def test_rename_detected(self):
        ctx = analyze_context_flow(_rename_trace())
        transforms = ctx.points[0].transformations if ctx.points else []
        types = [t["type"] for t in transforms]
        assert "rename" in types

    def test_type_change_detected(self):
        ctx = analyze_context_flow(_type_change_trace())
        transforms = ctx.points[0].transformations if ctx.points else []
        types = [t["type"] for t in transforms]
        assert "type_change" in types

    def test_no_transform_clean(self):
        ctx = analyze_context_flow(_no_transform_trace())
        transforms = ctx.points[0].transformations if ctx.points else []
        assert len(transforms) == 0

    def test_transformations_in_dict(self):
        ctx = analyze_context_flow(_summarization_trace())
        d = ctx.points[0].to_dict()
        assert "transformations" in d
        assert len(d["transformations"]) > 0

    def test_transform_has_detail(self):
        ctx = analyze_context_flow(_summarization_trace())
        for t in ctx.points[0].transformations:
            assert "type" in t
            assert "key" in t
            assert "detail" in t

    def test_empty_trace_no_crash(self):
        from agentguard.core.trace import ExecutionTrace
        t = ExecutionTrace(task="empty")
        t.complete()
        ctx = analyze_context_flow(t)
        assert ctx.handoff_count == 0
