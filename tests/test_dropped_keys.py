"""Tests for handoff dropped key detection (Q2)."""

from agentguard.analysis import analyze_context_flow
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


def _handoff_trace(sender_output, receiver_input):
    """Build trace with sender→receiver handoff for key comparison."""
    trace = ExecutionTrace(task="keys")
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


class TestDroppedKeys:
    def test_no_keys_dropped(self):
        """All keys preserved → no loss."""
        data = {"a": 1, "b": 2}
        trace = _handoff_trace(data, data)
        report = analyze_context_flow(trace)
        for p in report.points:
            assert p.keys_lost == [] or set(p.keys_lost) == set()

    def test_keys_dropped_detected(self):
        """Missing key in receiver → detected as lost."""
        trace = _handoff_trace(
            {"a": 1, "b": 2, "c": 3},
            {"a": 1},
        )
        report = analyze_context_flow(trace)
        assert len(report.points) >= 1
        lost = report.points[0].keys_lost
        assert "b" in lost or "c" in lost

    def test_loss_anomaly_set(self):
        """Dropped keys trigger 'loss' anomaly."""
        trace = _handoff_trace(
            {"important": "data", "also": "needed"},
            {"unrelated": "stuff"},
        )
        report = analyze_context_flow(trace)
        anomalies = [p for p in report.points if p.anomaly == "loss"]
        assert len(anomalies) >= 1

    def test_extra_keys_not_flagged_as_loss(self):
        """Receiver having extra keys is not loss."""
        trace = _handoff_trace(
            {"a": 1},
            {"a": 1, "extra": 2},
        )
        report = analyze_context_flow(trace)
        for p in report.points:
            assert "a" not in (p.keys_lost or [])

    def test_keys_lost_in_report(self):
        """Lost keys shown in text report."""
        trace = _handoff_trace(
            {"critical": "data", "dropped": "info"},
            {"critical": "data"},
        )
        report = analyze_context_flow(trace)
        text = report.to_report()
        assert "Lost keys" in text or "lost" in text.lower()

    def test_empty_sender_no_crash(self):
        """Empty sender output doesn't crash."""
        trace = _handoff_trace({}, {"x": 1})
        report = analyze_context_flow(trace)
        assert isinstance(report.handoff_count, int)
