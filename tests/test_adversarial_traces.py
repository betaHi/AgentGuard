"""Test: adversarial traces — contradictory timestamps, missing parents, etc.

Real-world traces from buggy instrumentation may contain invalid data.
Every module must handle these gracefully without crashes.
"""

from datetime import UTC, datetime, timedelta

from agentguard.analysis import (
    analyze_bottleneck,
    analyze_context_flow,
    analyze_cost_yield,
    analyze_decisions,
    analyze_failures,
    analyze_flow,
)
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.normalize import normalize_trace
from agentguard.propagation import analyze_propagation
from agentguard.scoring import score_trace
from agentguard.tree import tree_to_text
from agentguard.web.viewer import trace_to_html_string


def _trace_with_reversed_timestamps():
    """Span where ended_at < started_at (negative duration)."""
    t = ExecutionTrace(task="reversed timestamps")
    now = datetime.now(UTC)
    s = Span(
        span_type=SpanType.AGENT, name="backwards",
        started_at=(now + timedelta(hours=1)).isoformat(),
        ended_at=now.isoformat(),  # before start!
        status=SpanStatus.COMPLETED,
    )
    t.add_span(s)
    t.complete()
    return t


def _trace_with_orphan_spans():
    """Spans referencing non-existent parent IDs."""
    t = ExecutionTrace(task="orphans")
    t.add_span(Span(span_type=SpanType.AGENT, name="root", status=SpanStatus.COMPLETED,
                     started_at=datetime.now(UTC).isoformat(),
                     ended_at=datetime.now(UTC).isoformat()))
    t.add_span(Span(span_type=SpanType.AGENT, name="orphan",
                     parent_span_id="nonexistent-parent-id",
                     status=SpanStatus.COMPLETED,
                     started_at=datetime.now(UTC).isoformat(),
                     ended_at=datetime.now(UTC).isoformat()))
    t.complete()
    return t


def _trace_with_none_timestamps():
    """Spans with None started_at/ended_at."""
    t = ExecutionTrace(task="null times")
    t.add_span(Span(span_type=SpanType.AGENT, name="no_times",
                     started_at="", ended_at=None,
                     status=SpanStatus.COMPLETED))
    t.complete()
    return t


def _trace_with_duplicate_span_ids():
    """Two spans sharing the same span_id (corrupt data)."""
    t = ExecutionTrace(task="dup ids")
    s1 = Span(span_type=SpanType.AGENT, name="first", status=SpanStatus.COMPLETED,
              started_at=datetime.now(UTC).isoformat(),
              ended_at=datetime.now(UTC).isoformat())
    s2 = Span(span_type=SpanType.AGENT, name="second", status=SpanStatus.FAILED,
              span_id=s1.span_id,  # duplicate!
              started_at=datetime.now(UTC).isoformat(),
              ended_at=datetime.now(UTC).isoformat(),
              error="dup")
    t.add_span(s1)
    t.add_span(s2)
    t.complete()
    return t


def _trace_with_circular_parent():
    """Span is its own parent (self-reference)."""
    t = ExecutionTrace(task="self-ref")
    s = Span(span_type=SpanType.AGENT, name="loop",
             status=SpanStatus.COMPLETED,
             started_at=datetime.now(UTC).isoformat(),
             ended_at=datetime.now(UTC).isoformat())
    s.parent_span_id = s.span_id  # self-reference
    t.add_span(s)
    t.complete()
    return t


ALL_ADVERSARIAL = [
    _trace_with_reversed_timestamps,
    _trace_with_orphan_spans,
    _trace_with_none_timestamps,
    _trace_with_duplicate_span_ids,
    _trace_with_circular_parent,
]


class TestAdversarialAnalysis:
    """All analysis functions must not crash on adversarial input."""

    def _run_all(self, trace):
        analyze_failures(trace)
        analyze_flow(trace)
        analyze_bottleneck(trace)
        analyze_context_flow(trace)
        analyze_cost_yield(trace)
        analyze_decisions(trace)
        analyze_propagation(trace)
        score_trace(trace)

    def test_reversed_timestamps(self):
        self._run_all(_trace_with_reversed_timestamps())

    def test_orphan_spans(self):
        self._run_all(_trace_with_orphan_spans())

    def test_none_timestamps(self):
        self._run_all(_trace_with_none_timestamps())

    def test_duplicate_span_ids(self):
        self._run_all(_trace_with_duplicate_span_ids())

    def test_circular_parent(self):
        self._run_all(_trace_with_circular_parent())


class TestAdversarialViewer:
    def test_all_render_html(self):
        for factory in ALL_ADVERSARIAL:
            html = trace_to_html_string(factory())
            assert "<!DOCTYPE html>" in html


class TestAdversarialTree:
    def test_all_produce_tree(self):
        for factory in ALL_ADVERSARIAL:
            txt = tree_to_text(factory())
            assert isinstance(txt, str)


class TestAdversarialNormalize:
    def test_all_normalize(self):
        for factory in ALL_ADVERSARIAL:
            result = normalize_trace(factory())
            assert result is not None


class TestAdversarialSerialization:
    def test_all_serialize_to_json(self):
        import json
        for factory in ALL_ADVERSARIAL:
            j = factory().to_json()
            json.loads(j)  # must be valid JSON
