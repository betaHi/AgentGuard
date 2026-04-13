"""Tests for parallel pipeline example — verify parallel execution is captured."""

from datetime import UTC

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.flowgraph import build_flow_graph
from agentguard.propagation import analyze_propagation
from agentguard.scoring import score_trace


def _make_parallel_trace():
    """Build a trace with true parallel agents (overlapping times)."""
    from datetime import datetime, timedelta

    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=UTC)

    trace = ExecutionTrace(
        task="parallel_test",
        started_at=base.isoformat(),
        ended_at=(base + timedelta(seconds=10)).isoformat(),
        status=SpanStatus.COMPLETED,
    )

    # Coordinator
    trace.add_span(Span(span_id="coord", name="coordinator", span_type=SpanType.AGENT,
                        status=SpanStatus.COMPLETED,
                        started_at=base.isoformat(),
                        ended_at=(base + timedelta(seconds=10)).isoformat()))

    # 3 parallel researchers (overlapping time ranges)
    trace.add_span(Span(span_id="web", name="web_researcher", span_type=SpanType.AGENT,
                        parent_span_id="coord", status=SpanStatus.COMPLETED,
                        started_at=base.isoformat(),
                        ended_at=(base + timedelta(seconds=3)).isoformat(),
                        output_data={"results": [1, 2, 3]}))

    trace.add_span(Span(span_id="acad", name="academic_researcher", span_type=SpanType.AGENT,
                        parent_span_id="coord", status=SpanStatus.COMPLETED,
                        started_at=(base + timedelta(milliseconds=100)).isoformat(),
                        ended_at=(base + timedelta(seconds=4)).isoformat(),
                        output_data={"results": [4, 5]}))

    trace.add_span(Span(span_id="social", name="social_researcher", span_type=SpanType.AGENT,
                        parent_span_id="coord", status=SpanStatus.FAILED,
                        error="API rate limited",
                        started_at=(base + timedelta(milliseconds=200)).isoformat(),
                        ended_at=(base + timedelta(seconds=1)).isoformat()))

    # Sequential: merger after all researchers
    trace.add_span(Span(span_id="merge", name="merger", span_type=SpanType.AGENT,
                        parent_span_id="coord", status=SpanStatus.COMPLETED,
                        started_at=(base + timedelta(seconds=4)).isoformat(),
                        ended_at=(base + timedelta(seconds=5)).isoformat(),
                        input_data={"results": [1, 2, 3, 4, 5]}))

    # Handoffs
    for h_from, h_to in [("web_researcher", "merger"), ("academic_researcher", "merger"), ("social_researcher", "merger")]:
        trace.add_span(Span(name=f"{h_from} → {h_to}", span_type=SpanType.HANDOFF,
                           status=SpanStatus.COMPLETED,
                           handoff_from=h_from, handoff_to=h_to,
                           context_size_bytes=1000,
                           started_at=(base + timedelta(seconds=4)).isoformat(),
                           ended_at=(base + timedelta(seconds=4)).isoformat()))

    # Writer after merger
    trace.add_span(Span(span_id="writer", name="writer", span_type=SpanType.AGENT,
                        parent_span_id="coord", status=SpanStatus.COMPLETED,
                        started_at=(base + timedelta(seconds=5)).isoformat(),
                        ended_at=(base + timedelta(seconds=10)).isoformat()))

    return trace


class TestParallelDetection:
    """Verify that parallel execution is correctly detected."""

    def test_parallel_phases_detected(self):
        trace = _make_parallel_trace()
        graph = build_flow_graph(trace)

        # Should detect at least one parallel phase
        parallel_phases = [p for p in graph.phases if p.is_parallel]
        assert len(parallel_phases) >= 1, "No parallel phases detected!"

        # The parallel phase should contain the 3 researchers
        parallel_names = set()
        for p in parallel_phases:
            parallel_names.update(p.span_names)
        assert "web_researcher" in parallel_names or "academic_researcher" in parallel_names

    def test_max_parallelism(self):
        trace = _make_parallel_trace()
        graph = build_flow_graph(trace)
        assert graph.max_parallelism >= 2, f"Expected parallelism >= 2, got {graph.max_parallelism}"

    def test_critical_path(self):
        trace = _make_parallel_trace()
        graph = build_flow_graph(trace)
        assert len(graph.critical_path) >= 1

    def test_failure_contained(self):
        trace = _make_parallel_trace()
        prop = analyze_propagation(trace)

        # social_researcher failed but coordinator succeeded = contained
        assert prop.containment_rate > 0

    def test_multiple_handoffs_to_merger(self):
        trace = _make_parallel_trace()
        handoffs = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
        merger_handoffs = [h for h in handoffs if h.handoff_to == "merger"]
        assert len(merger_handoffs) == 3

    def test_sequential_after_parallel(self):
        trace = _make_parallel_trace()
        graph = build_flow_graph(trace)

        # Sequential fraction should be less than 100% (some parallel)
        assert graph.sequential_fraction < 1.0, "Expected some parallel execution"

    def test_scoring(self):
        trace = _make_parallel_trace()
        score = score_trace(trace)
        # Should get a reasonable score despite one failure
        assert score.overall > 30
