"""Test: context flow doesn't falsely report loss between parallel agents.

Independent parallel agents under the same coordinator with completely
different data should NOT be treated as a handoff chain.
"""

from agentguard.analysis import analyze_context_flow
from agentguard.builder import TraceBuilder


def _parallel_trace():
    """Two independent agents under coordinator — NOT a handoff."""
    return (TraceBuilder("parallel")
        .agent("coordinator", duration_ms=5000)
            .agent("web_researcher", duration_ms=2000,
                   input_data={"query": "web search"},
                   output_data={"web_results": ["r1", "r2", "r3"]})
            .end()
            .agent("academic_researcher", duration_ms=2000,
                   input_data={"query": "academic search"},
                   output_data={"papers": ["p1", "p2"]})
            .end()
            .agent("news_researcher", duration_ms=1500,
                   input_data={"query": "news search"},
                   output_data={"articles": ["a1"]})
            .end()
        .end()
        .build())


def _sequential_handoff_trace():
    """Two agents where receiver depends on sender — IS a handoff."""
    return (TraceBuilder("sequential")
        .agent("coordinator", duration_ms=5000)
            .agent("fetcher", duration_ms=1000,
                   output_data={"data": [1, 2, 3], "source": "api"})
            .end()
            .agent("processor", duration_ms=1000,
                   input_data={"data": [1, 2], "filter": "even"})
            .end()
        .end()
        .build())


class TestParallelContextFlow:
    def test_parallel_agents_no_false_loss(self):
        """Independent parallel agents should not show context loss."""
        ctx = analyze_context_flow(_parallel_trace())
        loss_points = [p for p in ctx.points if p.anomaly == "loss"]
        assert len(loss_points) == 0, (
            f"False loss detected: {[(p.from_agent, p.to_agent, p.keys_lost) for p in loss_points]}"
        )

    def test_parallel_agents_no_false_truncation(self):
        ctx = analyze_context_flow(_parallel_trace())
        trunc = [p for p in ctx.points if p.anomaly == "truncation"]
        assert len(trunc) == 0

    def test_sequential_handoff_still_detected(self):
        """Real handoffs with shared keys are still analyzed."""
        ctx = analyze_context_flow(_sequential_handoff_trace())
        # 'data' is shared between fetcher output and processor input
        assert ctx.handoff_count >= 1
        found = any(p.from_agent == "fetcher" and p.to_agent == "processor"
                     for p in ctx.points)
        assert found

    def test_parallel_no_anomalies(self):
        ctx = analyze_context_flow(_parallel_trace())
        assert len(ctx.anomalies) == 0

    def test_mixed_parallel_and_sequential(self):
        """Trace with both parallel and sequential agents."""
        t = (TraceBuilder("mixed")
            .agent("coordinator", duration_ms=8000)
                # Parallel pair (independent)
                .agent("search_a", duration_ms=1000,
                       output_data={"results_a": [1]})
                .end()
                .agent("search_b", duration_ms=1000,
                       input_data={"query_b": "different"},
                       output_data={"results_b": [2]})
                .end()
                # Sequential handoff
                .agent("merger", duration_ms=500,
                       input_data={"results_a": [1], "results_b": [2]},
                       output_data={"merged": [1, 2]})
                .end()
                .agent("formatter", duration_ms=200,
                       input_data={"merged": [1]})  # filtering
                .end()
            .end()
            .build())
        ctx = analyze_context_flow(t)
        # search_a → search_b should NOT be a handoff (no shared keys)
        false_handoffs = [p for p in ctx.points
                          if p.from_agent == "search_a" and p.to_agent == "search_b"]
        assert len(false_handoffs) == 0
        # merger → formatter SHOULD be detected (shared key 'merged')
        real_handoffs = [p for p in ctx.points
                         if p.from_agent == "merger" and p.to_agent == "formatter"]
        assert len(real_handoffs) == 1
