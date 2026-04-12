"""Tests for causal chain confidence scores in failure propagation."""

from agentguard.propagation import (
    analyze_propagation, _compute_link_confidence, CausalLink
)
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


def _make_span(name, span_type=SpanType.AGENT, parent_id=None,
               start="2025-01-01T00:00:00+00:00",
               end="2025-01-01T00:00:01+00:00",
               status=SpanStatus.COMPLETED, error=None):
    return Span(name=name, span_type=span_type, parent_span_id=parent_id,
                started_at=start, ended_at=end, status=status, error=error)


class TestLinkConfidence:
    def test_same_error_direct_child_high(self):
        """Same error + direct parent-child → high confidence."""
        parent = _make_span("p", status=SpanStatus.FAILED, error="ConnectionError: x",
                            start="2025-01-01T00:00:00+00:00",
                            end="2025-01-01T00:00:01+00:00")
        child = _make_span("c", parent_id=parent.span_id,
                           start="2025-01-01T00:00:01+00:00",
                           end="2025-01-01T00:00:02+00:00",
                           status=SpanStatus.FAILED, error="ConnectionError: x")
        conf = _compute_link_confidence(parent, child, {})
        assert conf >= 0.9

    def test_different_error_lowers_confidence(self):
        """Different error types → lower confidence."""
        parent = _make_span("p", status=SpanStatus.FAILED, error="ConnectionError: x")
        child = _make_span("c", parent_id=parent.span_id,
                           status=SpanStatus.FAILED, error="ValueError: bad")
        conf = _compute_link_confidence(parent, child, {})
        assert conf < 0.9

    def test_non_parent_child_lower(self):
        """Non-parent-child relationship → lower confidence."""
        parent = _make_span("p", status=SpanStatus.FAILED, error="Err: x")
        child = _make_span("c", status=SpanStatus.FAILED, error="Err: x")
        # child.parent_span_id is NOT parent.span_id
        conf = _compute_link_confidence(parent, child, {})
        assert conf < 0.7

    def test_confidence_bounded_0_to_1(self):
        """Confidence is always between 0 and 1."""
        parent = _make_span("p", status=SpanStatus.FAILED, error="Err")
        child = _make_span("c", parent_id=parent.span_id,
                           status=SpanStatus.FAILED, error="Err")
        conf = _compute_link_confidence(parent, child, {})
        assert 0.0 <= conf <= 1.0


class TestChainConfidence:
    def test_no_links_confidence_is_1(self):
        """Chain with no links (root only) has confidence 1.0."""
        trace = ExecutionTrace(task="t")
        trace.started_at = "2025-01-01T00:00:00+00:00"
        s = _make_span("solo", status=SpanStatus.FAILED, error="crash")
        trace.add_span(s)
        trace.ended_at = "2025-01-01T00:00:01+00:00"
        trace.status = SpanStatus.COMPLETED
        result = analyze_propagation(trace)
        assert len(result.causal_chains) == 1
        assert result.causal_chains[0].chain_confidence == 1.0

    def test_multi_link_chain_confidence_multiplies(self):
        """Chain confidence is product of link confidences."""
        trace = ExecutionTrace(task="t")
        trace.started_at = "2025-01-01T00:00:00+00:00"
        root = _make_span("root", status=SpanStatus.COMPLETED,
                          end="2025-01-01T00:00:03+00:00")
        trace.add_span(root)
        a = _make_span("a", parent_id=root.span_id,
                       status=SpanStatus.FAILED, error="Err: x")
        trace.add_span(a)
        b = _make_span("b", parent_id=a.span_id,
                       start="2025-01-01T00:00:01+00:00",
                       end="2025-01-01T00:00:02+00:00",
                       status=SpanStatus.FAILED, error="Err: x")
        trace.add_span(b)
        trace.ended_at = "2025-01-01T00:00:03+00:00"
        trace.status = SpanStatus.COMPLETED
        result = analyze_propagation(trace)
        chain = [c for c in result.causal_chains if c.root_span_name == "a"]
        assert len(chain) == 1
        assert chain[0].chain_confidence < 1.0
        assert chain[0].chain_confidence > 0.0

    def test_confidence_in_to_dict(self):
        """Confidence appears in serialized output."""
        trace = ExecutionTrace(task="t")
        trace.started_at = "2025-01-01T00:00:00+00:00"
        root = _make_span("root", status=SpanStatus.COMPLETED,
                          end="2025-01-01T00:00:02+00:00")
        trace.add_span(root)
        a = _make_span("a", parent_id=root.span_id,
                       status=SpanStatus.FAILED, error="Err")
        trace.add_span(a)
        trace.ended_at = "2025-01-01T00:00:02+00:00"
        trace.status = SpanStatus.COMPLETED
        result = analyze_propagation(trace)
        d = result.to_dict()
        assert "chain_confidence" in d["causal_chains"][0]

    def test_confidence_in_report_text(self):
        """Report shows chain confidence percentage."""
        trace = ExecutionTrace(task="t")
        trace.started_at = "2025-01-01T00:00:00+00:00"
        s = _make_span("fail", status=SpanStatus.FAILED, error="boom")
        trace.add_span(s)
        trace.ended_at = "2025-01-01T00:00:01+00:00"
        trace.status = SpanStatus.COMPLETED
        result = analyze_propagation(trace)
        text = result.to_report()
        assert "Chain confidence:" in text

    def test_no_failures_no_chains(self):
        """No failures → empty chains, no crash."""
        trace = ExecutionTrace(task="t")
        trace.started_at = "2025-01-01T00:00:00+00:00"
        s = _make_span("ok", status=SpanStatus.COMPLETED)
        trace.add_span(s)
        trace.ended_at = "2025-01-01T00:00:01+00:00"
        trace.status = SpanStatus.COMPLETED
        result = analyze_propagation(trace)
        assert result.causal_chains == []
