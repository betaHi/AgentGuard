"""Robustness tests — verify modules handle degraded/partial traces."""

import pytest

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _partial_trace():
    """Trace with minimal data — no timestamps, no metadata."""
    trace = ExecutionTrace(trace_id="partial", task="partial")
    trace.add_span(Span(span_id="s1", name="agent_a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED))
    trace.add_span(Span(span_id="s2", name="tool_1", span_type=SpanType.TOOL, status=SpanStatus.FAILED, error="err"))
    return trace


def _json_roundtrip_trace():
    """Trace that went through JSON serialization (from external source)."""
    trace = ExecutionTrace(trace_id="json", task="from_json")
    trace.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at="2026-04-12T00:00:00Z", ended_at="2026-04-12T00:00:01Z"))
    return ExecutionTrace.from_dict(trace.to_dict())


class TestModuleRobustness:
    """Every analysis module should handle partial traces without crashing."""

    @pytest.fixture(params=["partial", "json_roundtrip", "empty"])
    def trace(self, request):
        if request.param == "partial":
            return _partial_trace()
        elif request.param == "json_roundtrip":
            return _json_roundtrip_trace()
        else:
            return ExecutionTrace(task="empty")

    def test_scoring(self, trace):
        from agentguard.scoring import score_trace
        score = score_trace(trace)
        assert 0 <= score.overall <= 100

    def test_metrics(self, trace):
        from agentguard.metrics import extract_metrics
        m = extract_metrics(trace)
        assert m.span_count >= 0

    def test_timeline(self, trace):
        from agentguard.timeline import build_timeline
        tl = build_timeline(trace)
        assert isinstance(tl.events, list)

    def test_flow_graph(self, trace):
        from agentguard.flowgraph import build_flow_graph
        g = build_flow_graph(trace)
        assert isinstance(g.nodes, list)

    def test_propagation(self, trace):
        from agentguard.propagation import analyze_propagation
        r = analyze_propagation(trace)
        assert r.total_failures >= 0

    def test_correlations(self, trace):
        from agentguard.correlation import analyze_correlations
        r = analyze_correlations(trace)
        assert isinstance(r.fingerprints, list)

    def test_tree(self, trace):
        from agentguard.tree import compute_tree_stats, tree_to_text
        s = compute_tree_stats(trace)
        assert s.node_count >= 0
        text = tree_to_text(trace)
        assert isinstance(text, str)

    def test_normalize(self, trace):
        from agentguard.normalize import normalize_trace
        r = normalize_trace(trace)
        assert isinstance(r.changes, list)

    def test_summarize(self, trace):
        from agentguard.summarize import summarize_trace
        s = summarize_trace(trace)
        assert len(s) > 0

    def test_schema(self, trace):
        from agentguard.schema import validate_trace_dict
        errors = validate_trace_dict(trace.to_dict())
        assert isinstance(errors, list)

    def test_annotations(self, trace):
        from agentguard.annotations import auto_annotate
        store = auto_annotate(trace)
        assert store.count >= 0

    def test_dependency(self, trace):
        from agentguard.dependency import build_dependency_graph
        g = build_dependency_graph(trace)
        assert isinstance(g.agents, list)

    def test_context_flow(self, trace):
        from agentguard.context_flow import analyze_context_flow_deep
        r = analyze_context_flow_deep(trace)
        assert isinstance(r.transitions, list)

    def test_errors(self, trace):
        from agentguard.errors import analyze_errors
        r = analyze_errors(trace)
        assert r.total_errors >= 0

    def test_viewer(self, trace):
        from agentguard.web.viewer import trace_to_html_string
        html = trace_to_html_string(trace)
        assert "AgentGuard" in html
