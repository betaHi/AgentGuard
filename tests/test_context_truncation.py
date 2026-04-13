"""Tests for context truncation detection in handoff analysis."""

from agentguard.analysis import _detect_truncation, analyze_context_flow
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _make_sequential_trace(sender_output, receiver_input):
    """Build a trace with two sequential agents (sender → receiver)."""
    trace = ExecutionTrace(task="truncation test")
    trace.started_at = "2025-01-01T00:00:00+00:00"

    parent = Span(name="coordinator", span_type=SpanType.AGENT,
                  started_at="2025-01-01T00:00:00+00:00",
                  ended_at="2025-01-01T00:00:02+00:00",
                  status=SpanStatus.COMPLETED)
    trace.add_span(parent)

    sender = Span(name="sender", span_type=SpanType.AGENT,
                  parent_span_id=parent.span_id,
                  started_at="2025-01-01T00:00:00+00:00",
                  ended_at="2025-01-01T00:00:01+00:00",
                  status=SpanStatus.COMPLETED,
                  output_data=sender_output)
    trace.add_span(sender)

    receiver = Span(name="receiver", span_type=SpanType.AGENT,
                    parent_span_id=parent.span_id,
                    started_at="2025-01-01T00:00:01+00:00",
                    ended_at="2025-01-01T00:00:02+00:00",
                    status=SpanStatus.COMPLETED,
                    input_data=receiver_input)
    trace.add_span(receiver)

    trace.ended_at = "2025-01-01T00:00:02+00:00"
    trace.status = SpanStatus.COMPLETED
    return trace


class TestDetectTruncation:
    def test_list_truncation(self):
        """Detect when a list is shortened (prefix kept)."""
        is_trunc, desc = _detect_truncation(
            {"items": [1, 2, 3, 4, 5]},
            {"items": [1, 2, 3]},
        )
        assert is_trunc
        assert "5→3" in desc

    def test_string_truncation(self):
        """Detect when a string is cut (prefix kept)."""
        is_trunc, desc = _detect_truncation(
            {"text": "hello world this is long"},
            {"text": "hello world"},
        )
        assert is_trunc
        assert "chars" in desc

    def test_no_truncation_different_data(self):
        """Different data is not truncation."""
        is_trunc, _ = _detect_truncation(
            {"items": [1, 2, 3]},
            {"items": [4, 5, 6]},
        )
        assert not is_trunc

    def test_no_truncation_same_size(self):
        """Same-size data is not truncation."""
        is_trunc, _ = _detect_truncation(
            {"items": [1, 2, 3]},
            {"items": [1, 2, 3]},
        )
        assert not is_trunc

    def test_top_level_list_truncation(self):
        """Detect truncation of top-level lists."""
        is_trunc, desc = _detect_truncation(
            [1, 2, 3, 4, 5, 6],
            [1, 2, 3],
        )
        assert is_trunc
        assert "6→3" in desc

    def test_no_truncation_empty(self):
        """Empty inputs don't cause errors."""
        is_trunc, _ = _detect_truncation({}, {})
        assert not is_trunc

    def test_no_truncation_none(self):
        """None values don't crash."""
        is_trunc, _ = _detect_truncation(None, None)
        assert not is_trunc


class TestAnalyzeContextFlowTruncation:
    def test_truncation_detected_in_flow(self):
        """analyze_context_flow detects truncation between agents."""
        trace = _make_sequential_trace(
            sender_output={"articles": ["a1", "a2", "a3", "a4", "a5"]},
            receiver_input={"articles": ["a1", "a2"]},
        )
        report = analyze_context_flow(trace)
        truncation_points = [p for p in report.points if p.anomaly == "truncation"]
        assert len(truncation_points) >= 1
        assert "5→2" in truncation_points[0].truncation_detail

    def test_no_truncation_in_normal_flow(self):
        """Normal handoff without truncation shows as ok."""
        trace = _make_sequential_trace(
            sender_output={"data": [1, 2]},
            receiver_input={"data": [1, 2]},
        )
        report = analyze_context_flow(trace)
        truncation_points = [p for p in report.points if p.anomaly == "truncation"]
        assert len(truncation_points) == 0

    def test_truncation_in_report(self):
        """Truncation appears in the text report."""
        trace = _make_sequential_trace(
            sender_output={"items": list(range(10))},
            receiver_input={"items": list(range(3))},
        )
        report = analyze_context_flow(trace)
        text = report.to_report()
        assert "Truncated" in text or "truncat" in text.lower()

    def test_to_dict_includes_truncation(self):
        """to_dict includes truncation_detail field."""
        import json
        trace = _make_sequential_trace(
            sender_output={"x": [1, 2, 3, 4]},
            receiver_input={"x": [1, 2]},
        )
        report = analyze_context_flow(trace)
        d = report.to_dict()
        serialized = json.dumps(d)
        assert "truncation_detail" in serialized
