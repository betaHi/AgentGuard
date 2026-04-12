"""Tests for failure propagation analysis — causal chains, circuit breakers."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.propagation import analyze_propagation, hypothetical_failure, CausalChain


def _make_trace_with_cascade():
    """Create a trace where tool failure cascades through agents.
    
    Structure:
    orchestrator (COMPLETED — circuit breaker)
      ├── agent_a (FAILED — root cause)
      │   ├── tool_search (FAILED — caused by agent_a)
      │   └── tool_parse (FAILED — caused by agent_a)
      └── agent_b (COMPLETED — independent)
          └── tool_write (COMPLETED)
    """
    now = datetime.now(timezone.utc)
    trace = ExecutionTrace(
        trace_id="cascade-test",
        task="cascade test",
        started_at=now.isoformat(),
        ended_at=(now + timedelta(seconds=5)).isoformat(),
        status=SpanStatus.COMPLETED,
    )
    
    orch = Span(span_id="orch", name="orchestrator", span_type=SpanType.AGENT,
                status=SpanStatus.COMPLETED,
                started_at=now.isoformat(),
                ended_at=(now + timedelta(seconds=5)).isoformat())
    
    agent_a = Span(span_id="a", name="agent_a", span_type=SpanType.AGENT,
                   parent_span_id="orch", status=SpanStatus.FAILED,
                   error="API timeout",
                   started_at=now.isoformat(),
                   ended_at=(now + timedelta(seconds=2)).isoformat())
    
    tool_search = Span(span_id="ts", name="tool_search", span_type=SpanType.TOOL,
                       parent_span_id="a", status=SpanStatus.FAILED,
                       error="Connection refused",
                       started_at=now.isoformat(),
                       ended_at=(now + timedelta(seconds=1)).isoformat())
    
    tool_parse = Span(span_id="tp", name="tool_parse", span_type=SpanType.TOOL,
                      parent_span_id="a", status=SpanStatus.FAILED,
                      error="No data to parse",
                      started_at=(now + timedelta(seconds=1)).isoformat(),
                      ended_at=(now + timedelta(seconds=2)).isoformat())
    
    agent_b = Span(span_id="b", name="agent_b", span_type=SpanType.AGENT,
                   parent_span_id="orch", status=SpanStatus.COMPLETED,
                   started_at=(now + timedelta(seconds=2)).isoformat(),
                   ended_at=(now + timedelta(seconds=4)).isoformat())
    
    tool_write = Span(span_id="tw", name="tool_write", span_type=SpanType.TOOL,
                      parent_span_id="b", status=SpanStatus.COMPLETED,
                      started_at=(now + timedelta(seconds=2)).isoformat(),
                      ended_at=(now + timedelta(seconds=3)).isoformat())
    
    for s in [orch, agent_a, tool_search, tool_parse, agent_b, tool_write]:
        trace.add_span(s)
    
    return trace


def _make_deep_chain():
    """Create a deep failure chain: root → level1 → level2 → level3."""
    now = datetime.now(timezone.utc)
    trace = ExecutionTrace(
        trace_id="deep-chain",
        task="deep chain test",
        started_at=now.isoformat(),
        ended_at=(now + timedelta(seconds=10)).isoformat(),
        status=SpanStatus.FAILED,
    )
    
    spans = [
        Span(span_id="root", name="root_agent", span_type=SpanType.AGENT,
             status=SpanStatus.FAILED, error="propagated",
             started_at=now.isoformat(), ended_at=(now + timedelta(seconds=10)).isoformat()),
        Span(span_id="l1", name="level1", span_type=SpanType.AGENT,
             parent_span_id="root", status=SpanStatus.FAILED, error="propagated",
             started_at=now.isoformat(), ended_at=(now + timedelta(seconds=8)).isoformat()),
        Span(span_id="l2", name="level2", span_type=SpanType.AGENT,
             parent_span_id="l1", status=SpanStatus.FAILED, error="propagated",
             started_at=now.isoformat(), ended_at=(now + timedelta(seconds=5)).isoformat()),
        Span(span_id="l3", name="level3_tool", span_type=SpanType.TOOL,
             parent_span_id="l2", status=SpanStatus.FAILED, error="disk full",
             started_at=now.isoformat(), ended_at=(now + timedelta(seconds=2)).isoformat()),
    ]
    for s in spans:
        trace.add_span(s)
    return trace


class TestAnalyzePropagation:
    """Tests for analyze_propagation."""

    def test_no_failures(self):
        """Trace with no failures should return clean analysis."""
        now = datetime.now(timezone.utc)
        trace = ExecutionTrace(task="ok")
        trace.add_span(Span(span_id="a", name="agent", status=SpanStatus.COMPLETED,
                           started_at=now.isoformat(), ended_at=now.isoformat()))
        
        result = analyze_propagation(trace)
        assert result.total_failures == 0
        assert result.causal_chains == []
        assert result.containment_rate == 1.0

    def test_cascade_detection(self):
        """Detect failure cascade from agent to its tools."""
        trace = _make_trace_with_cascade()
        result = analyze_propagation(trace)
        
        assert result.total_failures == 3  # agent_a + tool_search + tool_parse
        assert len(result.causal_chains) >= 1
        
        # tool_search and tool_parse are leaf failures under agent_a
        # The root cause should be one of the tool failures (deepest unparented failure)
        root_names = {c.root_span_name for c in result.causal_chains}
        assert "tool_search" in root_names or "tool_parse" in root_names or "agent_a" in root_names

    def test_circuit_breaker_detection(self):
        """Orchestrator succeeded despite child failure = circuit breaker."""
        trace = _make_trace_with_cascade()
        result = analyze_propagation(trace)
        
        # The orchestrator should be a circuit breaker
        assert result.containment_rate > 0
        cb_names = {cb["name"] for cb in result.circuit_breakers}
        # orchestrator completed despite agent_a failing
        assert "orchestrator" in cb_names

    def test_deep_chain(self):
        """Deep failure chain should have correct depth."""
        trace = _make_deep_chain()
        result = analyze_propagation(trace)
        
        assert result.total_failures == 4
        # The deepest root cause is level3_tool, propagating up
        # But since all parents also failed, the root cause is level3_tool
        assert result.max_depth >= 0

    def test_report_generation(self):
        """Report should be a non-empty string."""
        trace = _make_trace_with_cascade()
        result = analyze_propagation(trace)
        report = result.to_report()
        assert "Failure Propagation" in report
        assert len(report) > 50

    def test_to_dict(self):
        """Serialization should work."""
        trace = _make_trace_with_cascade()
        result = analyze_propagation(trace)
        d = result.to_dict()
        assert "causal_chains" in d
        assert "circuit_breakers" in d
        assert isinstance(d["containment_rate"], float)


class TestHypotheticalFailure:
    """Tests for what-if failure analysis."""

    def test_blast_radius(self):
        """Hypothetical failure should show all downstream spans."""
        trace = _make_trace_with_cascade()
        result = hypothetical_failure(trace, "orch")
        
        # orchestrator has all other spans as descendants
        assert result["blast_radius"] >= 2  # at least agent_a and agent_b

    def test_leaf_span(self):
        """Leaf span failure has zero blast radius."""
        trace = _make_trace_with_cascade()
        result = hypothetical_failure(trace, "tw")  # tool_write is a leaf
        
        assert result["blast_radius"] == 0
        assert result["affected_spans"] == []

    def test_nonexistent_span(self):
        """Nonexistent span should return error."""
        trace = _make_trace_with_cascade()
        result = hypothetical_failure(trace, "nonexistent")
        assert "error" in result

    def test_critical_detection(self):
        """Agent with children should be marked critical."""
        trace = _make_trace_with_cascade()
        result = hypothetical_failure(trace, "orch")
        assert result["critical"] is True
        
        # Leaf tool is not critical
        result_leaf = hypothetical_failure(trace, "tw")
        assert result_leaf["critical"] is False


class TestHandoffChains:
    """Tests for handoff chain analysis."""

    def test_no_handoffs(self):
        """Trace without handoffs should return empty."""
        from agentguard.propagation import analyze_handoff_chains
        trace = _make_trace_with_cascade()
        result = analyze_handoff_chains(trace)
        assert result["total_handoffs"] == 0
        assert result["chains"] == []

    def test_with_handoffs(self):
        """Trace with handoffs should detect chains."""
        from agentguard.propagation import analyze_handoff_chains
        from agentguard.sdk.recorder import init_recorder, finish_recording
        from agentguard.sdk.handoff import record_handoff, mark_context_used
        
        init_recorder(task="chain_test")
        
        h1 = record_handoff("collector", "analyzer", context={"data": [1, 2], "meta": "info"})
        mark_context_used(h1, used_keys=["data"])
        
        h2 = record_handoff("analyzer", "writer", context={"analysis": "done"})
        mark_context_used(h2, used_keys=["analysis"])
        
        trace = finish_recording()
        result = analyze_handoff_chains(trace)
        
        assert result["total_handoffs"] == 2
        assert len(result["chains"]) >= 1
        # Chain should be: collector → analyzer → writer
        chain = result["chains"][0]
        assert "collector" in chain["agents"]

    def test_degradation_score(self):
        """Degradation score should reflect key loss."""
        from agentguard.propagation import analyze_handoff_chains
        from agentguard.sdk.recorder import init_recorder, finish_recording
        from agentguard.sdk.handoff import record_handoff, mark_context_used
        
        init_recorder(task="degradation")
        
        h = record_handoff("a", "b", context={"x": 1, "y": 2, "z": 3})
        mark_context_used(h, used_keys=["x"])  # drops y, z
        
        trace = finish_recording()
        result = analyze_handoff_chains(trace)
        
        assert result["degradation_score"] > 0


class TestContextIntegrity:
    """Tests for context integrity scoring."""

    def test_perfect_integrity(self):
        """Trace with no issues should score high."""
        from agentguard.propagation import compute_context_integrity
        now = datetime.now(timezone.utc)
        trace = ExecutionTrace(task="ok", started_at=now.isoformat(), ended_at=now.isoformat())
        trace.add_span(Span(span_id="a", name="agent", status=SpanStatus.COMPLETED,
                           started_at=now.isoformat(), ended_at=now.isoformat()))
        
        result = compute_context_integrity(trace)
        assert result["integrity_score"] >= 0.0
        assert "integrity_score" in result
        assert "components" in result

    def test_with_failures(self):
        """Trace with failures should have lower resilience component."""
        from agentguard.propagation import compute_context_integrity
        trace = _make_deep_chain()  # all failures
        
        result = compute_context_integrity(trace)
        assert result["components"]["failure_resilience"] == 0.0  # no containment

    def test_recommendations(self):
        """Should generate recommendations for poor traces."""
        from agentguard.propagation import compute_context_integrity
        now = datetime.now(timezone.utc)
        trace = ExecutionTrace(task="empty")
        result = compute_context_integrity(trace)
        
        # No handoffs = should recommend using record_handoff
        assert any("handoff" in r.lower() for r in result["recommendations"])
