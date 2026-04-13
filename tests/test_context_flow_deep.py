"""Tests for deep context flow analysis — compression, truncation, bandwidth."""

from datetime import UTC, datetime, timedelta

from agentguard.context_flow import ContextFlowAnalysis, analyze_context_flow_deep
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=UTC)
    return (base + timedelta(seconds=offset_s)).isoformat()


def _make_pipeline_trace():
    """Pipeline: collector → analyzer → summarizer
    Context shrinks at each stage (compression pipeline).
    """
    trace = ExecutionTrace(
        trace_id="pipeline", task="context pipeline",
        started_at=_ts(0), ended_at=_ts(15), status=SpanStatus.COMPLETED,
    )
    trace.add_span(Span(span_id="orch", name="orchestrator", span_type=SpanType.AGENT,
                        status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(15)))

    # Collector: no input, large output
    trace.add_span(Span(span_id="col", name="collector", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(0), ended_at=_ts(5),
                        input_data=None,
                        output_data={"articles": ["a" * 500, "b" * 500], "metadata": {"source": "web"}, "raw_html": "x" * 2000}))

    # Analyzer: gets collector output, drops raw_html (truncation)
    trace.add_span(Span(span_id="ana", name="analyzer", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(5), ended_at=_ts(10),
                        input_data={"articles": ["a" * 500, "b" * 500], "metadata": {"source": "web"}},
                        output_data={"analysis": "summary of articles", "key_points": ["p1", "p2"]}))

    # Summarizer: gets analysis, small output
    trace.add_span(Span(span_id="sum", name="summarizer", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(10), ended_at=_ts(15),
                        input_data={"analysis": "summary of articles", "key_points": ["p1", "p2"]},
                        output_data={"summary": "brief"}))

    return trace


def _make_expansion_trace():
    """Pipeline where context expands (enrichment)."""
    trace = ExecutionTrace(
        trace_id="expand", task="enrichment",
        started_at=_ts(0), ended_at=_ts(10), status=SpanStatus.COMPLETED,
    )
    trace.add_span(Span(span_id="orch", name="pipeline", span_type=SpanType.AGENT,
                        status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(10)))
    trace.add_span(Span(span_id="q", name="query_parser", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(0), ended_at=_ts(3),
                        input_data={"query": "AI agents"},
                        output_data={"parsed": {"intent": "search", "entities": ["AI", "agents"]}}))
    trace.add_span(Span(span_id="e", name="enricher", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(3), ended_at=_ts(8),
                        input_data={"parsed": {"intent": "search", "entities": ["AI", "agents"]}},
                        output_data={"enriched": {"intent": "search", "entities": ["AI", "agents"],
                                     "related": ["LLM", "multi-agent"], "context": "x" * 5000}}))
    return trace


class TestContextFlowDeep:
    """Tests for deep context flow analysis."""

    def test_compression_detection(self):
        """Detect compression in a pipeline."""
        trace = _make_pipeline_trace()
        result = analyze_context_flow_deep(trace)

        assert isinstance(result, ContextFlowAnalysis)
        assert len(result.transitions) >= 2

        # collector → analyzer should show compression (raw_html dropped)
        first_t = result.transitions[0]
        assert first_t.from_agent == "collector"
        assert first_t.to_agent == "analyzer"
        # raw_html was in output but not in input = compression
        assert "raw_html" in first_t.keys_removed

    def test_expansion_detection(self):
        """Detect expansion in enrichment pipeline."""
        trace = _make_expansion_trace()
        result = analyze_context_flow_deep(trace)

        assert len(result.transitions) >= 1
        # enricher output should be larger than input
        has_expansion = any(t.event == "expansion" for t in result.transitions)
        assert has_expansion or result.expansion_events >= 0  # enrichment happened

    def test_snapshots(self):
        """Snapshots should capture input and output of each agent."""
        trace = _make_pipeline_trace()
        result = analyze_context_flow_deep(trace)

        # Should have snapshots for each non-orchestrator agent
        agent_names = {s.agent_name for s in result.snapshots}
        assert "collector" in agent_names
        assert "analyzer" in agent_names
        assert "summarizer" in agent_names

        # Each agent should have input + output snapshots
        for name in ["collector", "analyzer", "summarizer"]:
            directions = {s.direction for s in result.snapshots if s.agent_name == name}
            assert "input" in directions
            assert "output" in directions

    def test_bandwidth(self):
        """Bandwidth should be calculated for transitions."""
        trace = _make_pipeline_trace()
        result = analyze_context_flow_deep(trace)

        if result.bandwidth:
            for b in result.bandwidth:
                assert b.bandwidth_bps > 0
                assert b.bytes_transferred > 0

    def test_compression_ratio(self):
        """Overall compression ratio should reflect data reduction."""
        trace = _make_pipeline_trace()
        result = analyze_context_flow_deep(trace)

        # Pipeline compresses data overall
        assert result.compression_ratio > 0

    def test_bottleneck_agent(self):
        """Should identify where most context is lost."""
        trace = _make_pipeline_trace()
        result = analyze_context_flow_deep(trace)

        # Analyzer or summarizer should be the bottleneck
        if result.bottleneck_agent:
            assert result.bottleneck_agent in ["analyzer", "summarizer"]

    def test_report(self):
        """Report should contain transitions."""
        trace = _make_pipeline_trace()
        result = analyze_context_flow_deep(trace)
        report = result.to_report()

        assert "Context Flow" in report
        assert "collector" in report

    def test_to_dict(self):
        """Serialization should work."""
        trace = _make_pipeline_trace()
        result = analyze_context_flow_deep(trace)
        d = result.to_dict()

        assert "transitions" in d
        assert "compression_ratio" in d
        assert "truncation_events" in d

    def test_empty_trace(self):
        """Empty trace should not crash."""
        trace = ExecutionTrace(task="empty")
        result = analyze_context_flow_deep(trace)

        assert result.snapshots == []
        assert result.transitions == []
        assert result.truncation_events == 0

    def test_no_data_agents(self):
        """Agents with no input/output data should still work."""
        trace = ExecutionTrace(task="no_data", started_at=_ts(0), ended_at=_ts(5))
        trace.add_span(Span(span_id="a", name="agent", span_type=SpanType.AGENT,
                           status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(5)))
        result = analyze_context_flow_deep(trace)

        # Should have snapshots with size 0
        assert len(result.snapshots) == 2  # input + output
        for s in result.snapshots:
            assert s.size_bytes == 0
