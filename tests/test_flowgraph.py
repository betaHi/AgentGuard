"""Tests for multi-agent flow graph — DAG, phases, critical path."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.flowgraph import build_flow_graph, FlowGraph


def _ts(offset_s: float = 0) -> str:
    """Create ISO timestamp with offset from a fixed base."""
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


def _make_sequential_trace():
    """Two agents running sequentially under an orchestrator."""
    trace = ExecutionTrace(
        trace_id="seq", task="sequential",
        started_at=_ts(0), ended_at=_ts(10), status=SpanStatus.COMPLETED,
    )
    trace.add_span(Span(span_id="orch", name="orchestrator", span_type=SpanType.AGENT,
                        status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(10)))
    trace.add_span(Span(span_id="a1", name="researcher", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(0), ended_at=_ts(5)))
    trace.add_span(Span(span_id="a2", name="writer", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(5), ended_at=_ts(10)))
    return trace


def _make_parallel_trace():
    """Two agents running in parallel under an orchestrator."""
    trace = ExecutionTrace(
        trace_id="par", task="parallel",
        started_at=_ts(0), ended_at=_ts(6), status=SpanStatus.COMPLETED,
    )
    trace.add_span(Span(span_id="orch", name="orchestrator", span_type=SpanType.AGENT,
                        status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(6)))
    trace.add_span(Span(span_id="a1", name="searcher", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(0), ended_at=_ts(4)))
    trace.add_span(Span(span_id="a2", name="fetcher", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(1), ended_at=_ts(5)))
    trace.add_span(Span(span_id="a3", name="merger", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(5), ended_at=_ts(6)))
    return trace


def _make_complex_trace():
    """Complex trace with mixed parallel and sequential execution + tools."""
    trace = ExecutionTrace(
        trace_id="complex", task="complex pipeline",
        started_at=_ts(0), ended_at=_ts(20), status=SpanStatus.COMPLETED,
    )
    # Orchestrator
    trace.add_span(Span(span_id="orch", name="pipeline", span_type=SpanType.AGENT,
                        status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(20)))
    # Phase 1: researcher (sequential)
    trace.add_span(Span(span_id="r", name="researcher", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(0), ended_at=_ts(5)))
    trace.add_span(Span(span_id="rs", name="web_search", span_type=SpanType.TOOL,
                        parent_span_id="r", status=SpanStatus.COMPLETED,
                        started_at=_ts(1), ended_at=_ts(4)))
    # Phase 2: analyst + coder (parallel)
    trace.add_span(Span(span_id="an", name="analyst", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(5), ended_at=_ts(12)))
    trace.add_span(Span(span_id="co", name="coder", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(6), ended_at=_ts(14)))
    # Phase 3: reviewer (sequential, after both)
    trace.add_span(Span(span_id="rv", name="reviewer", span_type=SpanType.AGENT,
                        parent_span_id="orch", status=SpanStatus.COMPLETED,
                        started_at=_ts(14), ended_at=_ts(20)))
    return trace


class TestBuildFlowGraph:
    """Tests for build_flow_graph."""

    def test_sequential_detection(self):
        """Sequential agents should have sequential edges."""
        trace = _make_sequential_trace()
        graph = build_flow_graph(trace)
        
        # Should have sequential edge from researcher → writer
        seq_edges = [e for e in graph.edges if e["type"] == "sequential"]
        assert len(seq_edges) >= 1
        
        # Sequential fraction should be high
        assert graph.sequential_fraction >= 0.5

    def test_parallel_detection(self):
        """Overlapping agents should be in the same phase."""
        trace = _make_parallel_trace()
        graph = build_flow_graph(trace)
        
        # Should detect parallel phase with searcher + fetcher
        parallel_phases = [p for p in graph.phases if p.is_parallel]
        assert len(parallel_phases) >= 1
        
        parallel_names = set()
        for p in parallel_phases:
            parallel_names.update(p.span_names)
        assert "searcher" in parallel_names or "fetcher" in parallel_names
        
        assert graph.max_parallelism >= 2

    def test_critical_path(self):
        """Critical path should be the longest chain."""
        trace = _make_sequential_trace()
        graph = build_flow_graph(trace)
        
        assert len(graph.critical_path) >= 1
        assert graph.critical_path_ms > 0

    def test_complex_phases(self):
        """Complex trace should have multiple phases."""
        trace = _make_complex_trace()
        graph = build_flow_graph(trace)
        
        assert len(graph.phases) >= 2
        assert graph.max_parallelism >= 2

    def test_node_count(self):
        """All agent/tool spans should become nodes."""
        trace = _make_complex_trace()
        graph = build_flow_graph(trace)
        
        agent_nodes = [n for n in graph.nodes if n.span_type == "agent"]
        assert len(agent_nodes) >= 4  # pipeline, researcher, analyst, coder, reviewer

    def test_mermaid_output(self):
        """Mermaid diagram should be valid."""
        trace = _make_sequential_trace()
        graph = build_flow_graph(trace)
        mermaid = graph.to_mermaid()
        
        assert "graph TD" in mermaid
        assert "orchestrator" in mermaid

    def test_report_output(self):
        """Report should contain key info."""
        trace = _make_complex_trace()
        graph = build_flow_graph(trace)
        report = graph.to_report()
        
        assert "Flow Graph" in report
        assert "parallelism" in report.lower() or "parallel" in report.lower()

    def test_to_dict(self):
        """Serialization should work."""
        trace = _make_parallel_trace()
        graph = build_flow_graph(trace)
        d = graph.to_dict()
        
        assert "nodes" in d
        assert "edges" in d
        assert "phases" in d
        assert "critical_path" in d
        assert isinstance(d["max_parallelism"], int)

    def test_empty_trace(self):
        """Empty trace should not crash."""
        trace = ExecutionTrace(task="empty")
        graph = build_flow_graph(trace)
        
        assert graph.nodes == []
        assert graph.edges == []
        assert graph.phases == []

    def test_single_agent(self):
        """Single agent trace should have 1 node, 0 edges."""
        trace = ExecutionTrace(task="single", started_at=_ts(0), ended_at=_ts(5))
        trace.add_span(Span(span_id="a", name="solo", span_type=SpanType.AGENT,
                           status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(5)))
        graph = build_flow_graph(trace)
        
        assert len(graph.nodes) == 1
        assert graph.max_parallelism == 1
