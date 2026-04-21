"""Tests for handoff dropped key detection (Q2)."""

from agentguard.analysis import analyze_context_flow
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


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

    def test_dropped_keys_lower_semantic_retention(self):
        """Dropped keys should materially reduce semantic retention."""
        trace = _handoff_trace(
            {"critical": "data", "dropped": "info", "another": "fact"},
            {"critical": "data"},
        )
        report = analyze_context_flow(trace)
        assert report.points[0].semantic_retention_score is not None
        assert report.points[0].semantic_retention_score < 0.6
        assert report.points[0].semantic_loss_reason

    def test_empty_sender_no_crash(self):
        """Empty sender output doesn't crash."""
        trace = _handoff_trace({}, {"x": 1})
        report = analyze_context_flow(trace)
        assert isinstance(report.handoff_count, int)

    def test_critical_keys_lost_are_called_out(self):
        """Heuristic critical keys should be surfaced separately in Q2 output."""
        trace = _handoff_trace(
            {"query": "refund order", "priority": "high", "notes": "extra"},
            {"notes": "extra"},
        )
        report = analyze_context_flow(trace)
        point = report.points[0]
        assert set(point.critical_keys_lost) == {"query", "priority"}
        assert point.semantic_retention_score is not None
        assert point.semantic_retention_score < 0.45
        assert "critical keys lost" in point.semantic_loss_reason

    def test_explicit_handoff_critical_keys_lost(self):
        """Explicit handoff metadata should drive critical-loss scoring."""
        trace = ExecutionTrace(task="explicit critical")
        handoff = Span(
            name="router → executor",
            span_type=SpanType.HANDOFF,
            status=SpanStatus.COMPLETED,
            handoff_from="router",
            handoff_to="executor",
            context_size_bytes=120,
            context_used_keys=["notes"],
            context_dropped_keys=["query", "priority"],
            context_received={"size_bytes": 40, "keys": ["notes"]},
            metadata={
                "handoff.context_keys": ["query", "priority", "notes"],
                "handoff.context_size_bytes": 120,
                "handoff.used_keys": ["notes"],
                "handoff.dropped_keys": ["query", "priority"],
                "handoff.critical_keys": ["query", "priority"],
            },
        )
        trace.add_span(handoff)
        trace.complete()

        report = analyze_context_flow(trace)
        point = report.points[0]
        assert point.critical_keys_sent == ["priority", "query"]
        assert point.critical_keys_lost == ["priority", "query"]
        assert point.semantic_retention_score is not None
        assert point.semantic_retention_score < 0.2
        assert "critical keys lost" in point.semantic_loss_reason

    def test_downstream_failure_increases_handoff_impact(self):
        """Critical semantic loss should be elevated when the receiver subtree fails."""
        trace = ExecutionTrace(task="downstream impact")
        parent = Span(name="coord", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        sender = Span(
            name="sender",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.COMPLETED,
            output_data={"query": "refund", "priority": "high", "notes": "keep"},
        )
        receiver = Span(
            name="receiver",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.FAILED,
            error="missing query",
            input_data={"notes": "keep"},
        )
        trace.add_span(parent)
        trace.add_span(sender)
        trace.add_span(receiver)
        trace.complete()

        report = analyze_context_flow(trace)
        point = report.points[0]
        assert point.downstream_impact_score is not None
        assert point.downstream_impact_score >= 0.9
        assert "downstream failure" in point.downstream_impact_reason
        assert "downstream impact" in point.semantic_loss_reason

    def test_downstream_quality_degradation_increases_handoff_impact(self):
        """Low-quality downstream output should be surfaced on suspicious handoffs."""
        trace = ExecutionTrace(task="downstream quality")
        parent = Span(name="coord", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        sender = Span(
            name="sender",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.COMPLETED,
            output_data={"query": "refund", "priority": "high", "notes": "keep"},
        )
        receiver = Span(
            name="receiver",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.COMPLETED,
            input_data={"notes": "keep"},
            output_data={"verdict": "regressed", "comparison": {"improved": 0, "regressed": 2}},
        )
        trace.add_span(parent)
        trace.add_span(sender)
        trace.add_span(receiver)
        trace.complete()

        report = analyze_context_flow(trace)
        point = report.points[0]
        assert point.downstream_impact_score is not None
        assert point.downstream_impact_score > 0.6
        assert "quality degraded" in point.downstream_impact_reason

    def test_reference_loss_reduces_semantic_retention_even_when_keys_survive(self):
        """Dropping cited evidence should count as semantic loss even with matching keys."""
        trace = _handoff_trace(
            {
                "top_documents": [
                    {"doc_id": "doc-1", "title": "one"},
                    {"doc_id": "doc-2", "title": "two"},
                    {"doc_id": "doc-3", "title": "three"},
                ],
                "source_map": {"doc-1": "u1", "doc-2": "u2", "doc-3": "u3"},
                "summary": "brief",
            },
            {
                "top_documents": [
                    {"doc_id": "doc-1", "title": "one"},
                    {"doc_id": "doc-2", "title": "two"},
                ],
                "source_map": {"doc-1": "u1", "doc-2": "u2"},
                "summary": "brief",
            },
        )

        report = analyze_context_flow(trace)
        point = report.points[0]
        assert point.keys_lost == []
        assert point.semantic_retention_score is not None
        assert point.semantic_retention_score < 0.8
        assert "lost evidence references" in point.semantic_loss_reason
