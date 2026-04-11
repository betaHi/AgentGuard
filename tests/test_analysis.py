"""Tests for trace analysis — failure propagation, flow analysis."""

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.analysis import analyze_failures, analyze_flow


def _make_failure_trace():
    """Create a trace where tool fails, one agent handles it, one doesn't."""
    trace = ExecutionTrace(task="failure-test")
    
    coord = Span(name="coordinator", span_type=SpanType.AGENT)
    
    # Agent A: tool fails but agent catches it (handled)
    agent_a = Span(name="agent-a", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
    tool_a = Span(name="search", span_type=SpanType.TOOL, parent_span_id=agent_a.span_id)
    tool_a.fail("ConnectionError: timeout")
    cache = Span(name="cache", span_type=SpanType.TOOL, parent_span_id=agent_a.span_id)
    cache.complete(output="cached data")
    agent_a.complete(output={"from_cache": True})  # succeeded despite tool failure
    
    # Agent B: tool fails and agent fails too (unhandled)
    agent_b = Span(name="agent-b", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
    tool_b = Span(name="search", span_type=SpanType.TOOL, parent_span_id=agent_b.span_id)
    tool_b.fail("ConnectionError: timeout")
    agent_b.fail("search failed")
    
    coord.complete()
    
    for s in [coord, agent_a, tool_a, cache, agent_b, tool_b]:
        trace.add_span(s)
    trace.complete()
    return trace


def test_failure_analysis_root_causes():
    """Identifies root causes correctly."""
    trace = _make_failure_trace()
    analysis = analyze_failures(trace)
    
    assert analysis.total_failed_spans == 3  # 2 tools + 1 agent
    assert len(analysis.root_causes) >= 1


def test_failure_analysis_handled_vs_unhandled():
    """Distinguishes handled from unhandled failures."""
    trace = _make_failure_trace()
    analysis = analyze_failures(trace)
    
    # tool_a failed but agent_a succeeded → handled
    # tool_b failed and agent_b failed → unhandled
    assert analysis.handled_count >= 1
    assert analysis.unhandled_count >= 1


def test_failure_analysis_resilience():
    """Resilience score reflects handled ratio."""
    trace = _make_failure_trace()
    analysis = analyze_failures(trace)
    
    assert 0 <= analysis.resilience_score <= 1


def test_failure_analysis_no_failures():
    """No failures = perfect resilience."""
    trace = ExecutionTrace(task="clean")
    span = Span(name="agent", span_type=SpanType.AGENT)
    span.complete()
    trace.add_span(span)
    trace.complete()
    
    analysis = analyze_failures(trace)
    assert analysis.total_failed_spans == 0
    assert analysis.resilience_score == 1.0


def test_failure_report():
    """Failure analysis generates readable report."""
    trace = _make_failure_trace()
    analysis = analyze_failures(trace)
    report = analysis.to_report()
    assert "Failure Propagation" in report
    assert "Root cause" in report


def _make_flow_trace():
    """Create a multi-agent trace with handoffs."""
    trace = ExecutionTrace(task="flow-test")
    
    coord = Span(name="coordinator", span_type=SpanType.AGENT)
    
    agent_a = Span(name="researcher", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
    tool = Span(name="search", span_type=SpanType.TOOL, parent_span_id=agent_a.span_id)
    tool.complete(output=["data"])
    agent_a.complete(output={"results": ["data"], "topic": "AI"})
    
    agent_b = Span(name="analyst", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
    agent_b.complete(output={"analysis": "done"})
    
    coord.complete()
    
    for s in [coord, agent_a, tool, agent_b]:
        trace.add_span(s)
    trace.complete()
    return trace


def test_flow_analysis_handoffs():
    """Detects handoffs between sequential agents."""
    trace = _make_flow_trace()
    flow = analyze_flow(trace)
    
    assert flow.agent_count == 3
    assert len(flow.handoffs) >= 1
    assert flow.handoffs[0].from_agent == "researcher"
    assert flow.handoffs[0].to_agent == "analyst"


def test_flow_analysis_critical_path():
    """Identifies critical path."""
    trace = _make_flow_trace()
    flow = analyze_flow(trace)
    
    assert len(flow.critical_path) > 0
    assert "coordinator" in flow.critical_path


def test_flow_analysis_context_tracking():
    """Handoff includes context size information."""
    trace = _make_flow_trace()
    flow = analyze_flow(trace)
    
    if flow.handoffs:
        h = flow.handoffs[0]
        assert h.context_size_bytes > 0
        assert isinstance(h.context_keys, list)
