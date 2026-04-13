"""Tests for failure timeline ASCII visualization (Q3)."""

from agentguard.ascii_viz import failure_timeline
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _trace_with_failures():
    trace = ExecutionTrace(task="timeline")
    trace.started_at = "2025-01-01T00:00:00+00:00"
    root = Span(name="coord", span_type=SpanType.AGENT,
                started_at="2025-01-01T00:00:00+00:00",
                ended_at="2025-01-01T00:00:05+00:00",
                status=SpanStatus.COMPLETED)
    trace.add_span(root)
    f1 = Span(name="api_call", span_type=SpanType.TOOL,
              parent_span_id=root.span_id,
              started_at="2025-01-01T00:00:01+00:00",
              ended_at="2025-01-01T00:00:02+00:00",
              status=SpanStatus.FAILED, error="timeout")
    trace.add_span(f1)
    f2 = Span(name="orphan", span_type=SpanType.AGENT,
              started_at="2025-01-01T00:00:03+00:00",
              ended_at="2025-01-01T00:00:04+00:00",
              status=SpanStatus.FAILED, error="crash")
    trace.add_span(f2)
    trace.ended_at = "2025-01-01T00:00:05+00:00"
    trace.status = SpanStatus.COMPLETED
    return trace


class TestFailureTimeline:
    def test_shows_failed_spans(self):
        text = failure_timeline(_trace_with_failures())
        assert "api_call" in text
        assert "orphan" in text

    def test_contained_marker(self):
        text = failure_timeline(_trace_with_failures())
        assert "🛡" in text  # api_call is contained by coord

    def test_uncontained_marker(self):
        text = failure_timeline(_trace_with_failures())
        assert "✗" in text  # orphan has no parent

    def test_no_failures(self):
        trace = ExecutionTrace(task="ok")
        trace.started_at = "2025-01-01T00:00:00+00:00"
        s = Span(name="good", span_type=SpanType.AGENT,
                 started_at="2025-01-01T00:00:00+00:00",
                 ended_at="2025-01-01T00:00:01+00:00",
                 status=SpanStatus.COMPLETED)
        trace.add_span(s)
        trace.ended_at = "2025-01-01T00:00:01+00:00"
        trace.status = SpanStatus.COMPLETED
        text = failure_timeline(trace)
        assert "No failures" in text

    def test_bar_chars_present(self):
        text = failure_timeline(_trace_with_failures())
        assert "▓" in text

    def test_summary_counts(self):
        text = failure_timeline(_trace_with_failures())
        assert "Total failures: 2" in text
        assert "contained: 1" in text
        assert "uncontained: 1" in text
