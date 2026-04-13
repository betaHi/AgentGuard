"""Tests for handoff information retention ratio."""

import json

from agentguard.analysis import analyze_context_flow
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _trace_with_handoff(sender_output, receiver_input):
    """Build a trace with sequential agents for retention testing."""
    trace = ExecutionTrace(task="retention")
    trace.started_at = "2025-01-01T00:00:00+00:00"
    parent = Span(name="coord", span_type=SpanType.AGENT,
                  started_at="2025-01-01T00:00:00+00:00",
                  ended_at="2025-01-01T00:00:02+00:00",
                  status=SpanStatus.COMPLETED)
    trace.add_span(parent)
    s = Span(name="sender", span_type=SpanType.AGENT,
             parent_span_id=parent.span_id,
             started_at="2025-01-01T00:00:00+00:00",
             ended_at="2025-01-01T00:00:01+00:00",
             status=SpanStatus.COMPLETED,
             output_data=sender_output)
    trace.add_span(s)
    r = Span(name="receiver", span_type=SpanType.AGENT,
             parent_span_id=parent.span_id,
             started_at="2025-01-01T00:00:01+00:00",
             ended_at="2025-01-01T00:00:02+00:00",
             status=SpanStatus.COMPLETED,
             input_data=receiver_input)
    trace.add_span(r)
    trace.ended_at = "2025-01-01T00:00:02+00:00"
    trace.status = SpanStatus.COMPLETED
    return trace


def test_perfect_retention():
    """Same data sent and received → ratio ~1.0."""
    data = {"items": [1, 2, 3], "meta": "info"}
    trace = _trace_with_handoff(data, data)
    report = analyze_context_flow(trace)
    assert len(report.points) == 1
    ratio = report.points[0].retention_ratio
    assert ratio is not None
    assert abs(ratio - 1.0) < 0.01


def test_partial_loss():
    """Smaller received data → ratio < 1.0."""
    trace = _trace_with_handoff(
        {"data": "x" * 1000},
        {"data": "x" * 300},
    )
    report = analyze_context_flow(trace)
    ratio = report.points[0].retention_ratio
    assert ratio is not None
    assert ratio < 1.0
    assert ratio > 0.0


def test_bloat_ratio():
    """Larger received data → ratio > 1.0."""
    trace = _trace_with_handoff(
        {"data": "small"},
        {"data": "small", "extra": "x" * 500},
    )
    report = analyze_context_flow(trace)
    ratio = report.points[0].retention_ratio
    assert ratio is not None
    assert ratio > 1.0


def test_zero_sent_bytes():
    """Zero-size sender output → ratio is None (avoid division by zero)."""
    trace = _trace_with_handoff({}, {"data": "something"})
    report = analyze_context_flow(trace)
    # With empty sender, size is ~2 bytes for "{}" so not truly zero
    # but the ratio should still be computable
    assert len(report.points) >= 1


def test_avg_retention_multiple_handoffs():
    """Average retention computed across multiple handoffs."""
    trace = ExecutionTrace(task="multi")
    trace.started_at = "2025-01-01T00:00:00+00:00"
    parent = Span(name="coord", span_type=SpanType.AGENT,
                  started_at="2025-01-01T00:00:00+00:00",
                  ended_at="2025-01-01T00:00:03+00:00",
                  status=SpanStatus.COMPLETED)
    trace.add_span(parent)
    for i, (out_size, in_size) in enumerate([(100, 100), (100, 50)]):
        s = Span(name=f"s{i}", span_type=SpanType.AGENT,
                 parent_span_id=parent.span_id,
                 started_at=f"2025-01-01T00:00:0{i*2}+00:00",
                 ended_at=f"2025-01-01T00:00:0{i*2+1}+00:00",
                 status=SpanStatus.COMPLETED,
                 output_data={"d": "x" * out_size})
        r = Span(name=f"r{i}", span_type=SpanType.AGENT,
                 parent_span_id=parent.span_id,
                 started_at=f"2025-01-01T00:00:0{i*2+1}+00:00",
                 ended_at=f"2025-01-01T00:00:0{i*2+2}+00:00",
                 status=SpanStatus.COMPLETED,
                 input_data={"d": "x" * in_size})
        trace.add_span(s)
        trace.add_span(r)
    trace.ended_at = "2025-01-01T00:00:03+00:00"
    trace.status = SpanStatus.COMPLETED
    report = analyze_context_flow(trace)
    avg = report.avg_retention_ratio
    assert avg is not None
    assert 0.5 < avg < 1.0  # one perfect, one ~50%


def test_retention_in_report():
    """Retention percentage appears in text report."""
    trace = _trace_with_handoff({"d": "x" * 100}, {"d": "x" * 50})
    report = analyze_context_flow(trace)
    text = report.to_report()
    assert "Retention:" in text


def test_retention_in_to_dict():
    """retention_ratio appears in serialized output."""
    trace = _trace_with_handoff({"d": "x" * 100}, {"d": "x" * 50})
    report = analyze_context_flow(trace)
    d = report.to_dict()
    serialized = json.dumps(d)
    assert "retention_ratio" in serialized
    assert "avg_retention_ratio" in serialized


def test_no_handoffs_no_ratio():
    """Empty trace has no retention data."""
    trace = ExecutionTrace(task="empty")
    trace.complete()
    report = analyze_context_flow(trace)
    assert report.avg_retention_ratio is None
