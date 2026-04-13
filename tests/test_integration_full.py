"""Integration test — run a full pipeline through all analysis modules.

This is the "smoke test" that ensures all modules work together
on a realistic trace without crashing.
"""

import pytest

from agentguard.ab_test import ab_test
from agentguard.aggregate import aggregate_traces
from agentguard.annotations import auto_annotate
from agentguard.builder import TraceBuilder
from agentguard.comparison import compare_traces
from agentguard.context_flow import analyze_context_flow_deep
from agentguard.core.trace import SpanStatus, SpanType
from agentguard.correlation import analyze_correlations
from agentguard.diff import diff_context_flow, diff_flow_graphs, diff_traces
from agentguard.filter import by_status, by_type, filter_spans
from agentguard.flowgraph import build_flow_graph
from agentguard.metrics import extract_metrics
from agentguard.normalize import normalize_trace
from agentguard.profile import build_agent_profiles
from agentguard.propagation import analyze_handoff_chains, analyze_propagation, compute_context_integrity
from agentguard.schema import validate_trace_dict

# Analysis modules
from agentguard.scoring import score_trace
from agentguard.summarize import summarize_brief, summarize_trace
from agentguard.timeline import build_timeline
from agentguard.tree import compute_tree_stats, tree_to_text


@pytest.fixture
def complex_trace():
    """Build a realistic multi-agent pipeline trace."""
    return (TraceBuilder("Integration test: Research and write blog post")
        .agent("orchestrator", duration_ms=30000,
               output_data={"plan": "research then write"})
            .agent("researcher", duration_ms=8000,
                   input_data={"topic": "AI agents"},
                   output_data={"articles": ["a1", "a2"], "raw": "x" * 2000, "metadata": {"count": 2}},
                   token_count=2000, cost_usd=0.06)
                .tool("web_search", duration_ms=3000)
                .tool("pdf_parser", duration_ms=2000, retry_count=2)
                .llm_call("claude-extract", duration_ms=2500, token_count=1500, cost_usd=0.04)
            .end()
            .handoff("researcher", "analyst", context_size=3000, dropped_keys=["raw"])
            .agent("analyst", duration_ms=6000,
                   input_data={"articles": ["a1", "a2"], "metadata": {"count": 2}},
                   output_data={"insights": ["i1", "i2"]},
                   token_count=3000, cost_usd=0.09)
                .llm_call("claude-analyze", duration_ms=4000, token_count=2500, cost_usd=0.08)
            .end()
            .handoff("analyst", "writer", context_size=1500)
            .agent("writer", duration_ms=10000,
                   input_data={"insights": ["i1", "i2"]},
                   output_data={"draft": "# Blog Post"},
                   token_count=5000, cost_usd=0.15)
                .llm_call("claude-write", duration_ms=8000, token_count=4000, cost_usd=0.12)
            .end()
            .agent("reviewer", duration_ms=3000, status="failed", error="Service unavailable")
                .tool("grammar_check", duration_ms=500, status="failed", error="Connection refused")
            .end()
        .end()
        .build())


@pytest.fixture
def simple_trace():
    """Simple trace for comparison."""
    return (TraceBuilder("Simple task")
        .agent("worker", duration_ms=2000, output_data={"result": "done"})
            .tool("fetch", duration_ms=1000)
        .end()
        .build())


class TestFullIntegration:
    """Run every analysis module on the complex trace."""

    def test_scoring(self, complex_trace):
        score = score_trace(complex_trace)
        assert 0 <= score.overall <= 100
        assert score.grade in ("A", "B", "C", "D", "F")
        assert len(score.components) == 5

    def test_metrics(self, complex_trace):
        m = extract_metrics(complex_trace)
        assert m.span_count > 0
        assert m.agent_count >= 4
        assert m.total_tokens > 0
        assert m.total_cost_usd > 0

    def test_timeline(self, complex_trace):
        tl = build_timeline(complex_trace)
        assert len(tl.events) > 0
        text = tl.to_text()
        assert "researcher" in text

    def test_flow_graph(self, complex_trace):
        graph = build_flow_graph(complex_trace)
        assert len(graph.nodes) > 0
        mermaid = graph.to_mermaid()
        assert "graph TD" in mermaid

    def test_propagation(self, complex_trace):
        result = analyze_propagation(complex_trace)
        assert result.total_failures >= 2  # reviewer + grammar_check

    def test_context_integrity(self, complex_trace):
        result = compute_context_integrity(complex_trace)
        assert 0 <= result["integrity_score"] <= 1

    def test_handoff_chains(self, complex_trace):
        result = analyze_handoff_chains(complex_trace)
        assert result["total_handoffs"] >= 2

    def test_context_flow(self, complex_trace):
        result = analyze_context_flow_deep(complex_trace)
        assert len(result.snapshots) > 0

    def test_correlations(self, complex_trace):
        result = analyze_correlations(complex_trace)
        assert len(result.fingerprints) > 0

    def test_annotations(self, complex_trace):
        store = auto_annotate(complex_trace)
        assert store.count > 0  # should flag failures at minimum

    def test_filter(self, complex_trace):
        failed = filter_spans(complex_trace, by_status(SpanStatus.FAILED))
        assert len(failed) >= 2
        agents = filter_spans(complex_trace, by_type(SpanType.AGENT))
        assert len(agents) >= 4

    def test_tree(self, complex_trace):
        stats = compute_tree_stats(complex_trace)
        assert stats.depth >= 2
        text = tree_to_text(complex_trace)
        assert "orchestrator" in text

    def test_normalize(self, complex_trace):
        result = normalize_trace(complex_trace)
        assert isinstance(result.changes, list)

    def test_summarize(self, complex_trace):
        summary = summarize_trace(complex_trace)
        assert len(summary) > 50
        brief = summarize_brief(complex_trace)
        assert len(brief) > 10

    def test_schema(self, complex_trace):
        errors = validate_trace_dict(complex_trace.to_dict())
        assert errors == []

    def test_comparison(self, complex_trace, simple_trace):
        result = compare_traces(simple_trace, complex_trace)
        assert isinstance(result.score_delta, float)

    def test_diff(self, complex_trace, simple_trace):
        result = diff_traces(simple_trace, complex_trace)
        assert len(result.to_report()) > 0

    def test_diff_flow(self, complex_trace, simple_trace):
        result = diff_flow_graphs(simple_trace, complex_trace)
        assert "changes" in result

    def test_diff_context(self, complex_trace, simple_trace):
        result = diff_context_flow(simple_trace, complex_trace)
        assert "changes" in result

    def test_aggregate(self, complex_trace, simple_trace):
        result = aggregate_traces([complex_trace, simple_trace])
        assert result.trace_count == 2

    def test_ab_test(self, complex_trace, simple_trace):
        result = ab_test([simple_trace], [complex_trace])
        assert result.winner in ("a", "b", "tie")

    def test_profiles(self, complex_trace, simple_trace):
        profiles = build_agent_profiles([complex_trace, simple_trace])
        assert "researcher" in profiles
        assert "worker" in profiles

    def test_serialization_roundtrip(self, complex_trace):
        """Trace should survive JSON roundtrip."""
        from agentguard.core.trace import ExecutionTrace
        json_str = complex_trace.to_json()
        restored = ExecutionTrace.from_json(json_str)
        assert len(restored.spans) == len(complex_trace.spans)
        assert restored.task == complex_trace.task
