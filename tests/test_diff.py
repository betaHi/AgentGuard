"""Tests for trace diff."""

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.diff import diff_traces


def test_diff_no_changes():
    """Identical traces produce no diffs."""
    t = ExecutionTrace(task="test")
    s = Span(name="agent", span_type=SpanType.AGENT)
    s.complete()
    t.add_span(s)
    t.complete()
    
    result = diff_traces(t, t)
    assert not result.has_changes


def test_diff_status_regression():
    """Detects when a span goes from pass to fail."""
    t1 = ExecutionTrace(task="test")
    s1 = Span(name="agent", span_type=SpanType.AGENT)
    s1.complete()
    t1.add_span(s1)
    
    t2 = ExecutionTrace(task="test")
    s2 = Span(name="agent", span_type=SpanType.AGENT)
    s2.fail("broke")
    t2.add_span(s2)
    
    result = diff_traces(t1, t2)
    assert len(result.regressions) >= 1


def test_diff_status_improvement():
    """Detects when a span goes from fail to pass."""
    t1 = ExecutionTrace(task="test")
    s1 = Span(name="agent", span_type=SpanType.AGENT)
    s1.fail("error")
    t1.add_span(s1)
    
    t2 = ExecutionTrace(task="test")
    s2 = Span(name="agent", span_type=SpanType.AGENT)
    s2.complete()
    t2.add_span(s2)
    
    result = diff_traces(t1, t2)
    assert len(result.improvements) >= 1


def test_diff_span_added():
    """Detects new spans in candidate trace."""
    t1 = ExecutionTrace(task="test")
    t1.add_span(Span(name="agent-a", span_type=SpanType.AGENT))
    
    t2 = ExecutionTrace(task="test")
    t2.add_span(Span(name="agent-a", span_type=SpanType.AGENT))
    t2.add_span(Span(name="agent-b", span_type=SpanType.AGENT))
    
    result = diff_traces(t1, t2)
    assert "agent-b (agent)" in result.spans_added


def test_diff_report():
    """Diff report is readable."""
    t1 = ExecutionTrace(task="before")
    s = Span(name="agent", span_type=SpanType.AGENT)
    s.complete()
    t1.add_span(s)
    
    t2 = ExecutionTrace(task="after")
    s2 = Span(name="agent", span_type=SpanType.AGENT)
    s2.fail("new error")
    t2.add_span(s2)
    
    result = diff_traces(t1, t2)
    report = result.to_report()
    assert "Trace Diff" in report
    assert "Regressions" in report or "regressed" in report.lower()


class TestDiffFlowGraphs:
    """Tests for flow graph comparison."""

    def test_same_traces(self):
        """Identical traces should have no flow changes."""
        from agentguard.diff import diff_flow_graphs
        from datetime import datetime, timezone, timedelta
        
        now = datetime.now(timezone.utc)
        trace = ExecutionTrace(task="same", started_at=now.isoformat(), ended_at=(now + timedelta(seconds=5)).isoformat())
        trace.add_span(Span(name="a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                           started_at=now.isoformat(), ended_at=(now + timedelta(seconds=5)).isoformat()))
        
        result = diff_flow_graphs(trace, trace)
        assert result["changes"] == [] or all(c["type"] not in ("nodes_added", "nodes_removed") for c in result["changes"])

    def test_different_agents(self):
        """Traces with different agents should detect added/removed nodes."""
        from agentguard.diff import diff_flow_graphs
        from datetime import datetime, timezone, timedelta
        
        now = datetime.now(timezone.utc)
        
        trace_a = ExecutionTrace(task="a", started_at=now.isoformat(), ended_at=(now + timedelta(seconds=5)).isoformat())
        trace_a.add_span(Span(name="agent_x", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                             started_at=now.isoformat(), ended_at=(now + timedelta(seconds=5)).isoformat()))
        
        trace_b = ExecutionTrace(task="b", started_at=now.isoformat(), ended_at=(now + timedelta(seconds=5)).isoformat())
        trace_b.add_span(Span(name="agent_y", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                             started_at=now.isoformat(), ended_at=(now + timedelta(seconds=5)).isoformat()))
        
        result = diff_flow_graphs(trace_a, trace_b)
        change_types = {c["type"] for c in result["changes"]}
        assert "nodes_added" in change_types or "nodes_removed" in change_types


class TestDiffContextFlow:
    """Tests for context flow comparison."""

    def test_basic_diff(self):
        """Context flow diff should return a dict."""
        from agentguard.diff import diff_context_flow
        
        trace = ExecutionTrace(task="test")
        result = diff_context_flow(trace, trace)
        
        assert "changes" in result
        assert "flow_a" in result
        assert "flow_b" in result
