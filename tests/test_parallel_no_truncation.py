"""Test: parallel pipeline context flow does NOT report truncation
between independent parallel agents.

Regression test for the bug where analyze_context_flow compared
sequential siblings as if they were a handoff chain, causing false
'loss' and 'truncation' anomalies between independent parallel agents.
"""

from agentguard.analysis import analyze_context_flow
from agentguard.builder import TraceBuilder


def _fan_out_trace():
    """3 independent researchers under one coordinator — fan-out pattern."""
    return (TraceBuilder("parallel research")
        .agent("coordinator", duration_ms=8000,
               input_data={"task": "comprehensive research"})
            .agent("web_researcher", duration_ms=2000,
                   input_data={"source": "web"},
                   output_data={"web_results": ["page1", "page2", "page3"],
                                "confidence": 0.85})
            .end()
            .agent("academic_researcher", duration_ms=3000,
                   input_data={"source": "papers"},
                   output_data={"papers": ["arxiv:2401.001"],
                                "citations": 42})
            .end()
            .agent("news_researcher", duration_ms=1500,
                   input_data={"source": "news"},
                   output_data={"articles": ["headline1"],
                                "recency": "2024-01-15"})
            .end()
        .end()
        .build())


def _fan_out_with_different_sizes():
    """Parallel agents with vastly different output sizes — must NOT flag truncation."""
    return (TraceBuilder("size mismatch")
        .agent("coordinator", duration_ms=5000)
            .agent("big_agent", duration_ms=1000,
                   input_data={"mode": "full"},
                   output_data={"data": "x" * 10000, "count": 500})
            .end()
            .agent("small_agent", duration_ms=500,
                   input_data={"mode": "summary"},
                   output_data={"summary": "brief"})
            .end()
            .agent("medium_agent", duration_ms=800,
                   input_data={"mode": "filtered"},
                   output_data={"items": list(range(50))})
            .end()
        .end()
        .build())


class TestParallelNoTruncation:
    def test_no_truncation_in_fan_out(self):
        """Fan-out pattern must not flag truncation."""
        ctx = analyze_context_flow(_fan_out_trace())
        trunc = [p for p in ctx.points if p.anomaly == "truncation"]
        assert len(trunc) == 0, f"False truncation: {trunc}"

    def test_no_loss_in_fan_out(self):
        """Fan-out pattern must not flag key loss."""
        ctx = analyze_context_flow(_fan_out_trace())
        loss = [p for p in ctx.points if p.anomaly == "loss"]
        assert len(loss) == 0, f"False loss: {loss}"

    def test_no_compression_in_fan_out(self):
        """Fan-out pattern must not flag compression."""
        ctx = analyze_context_flow(_fan_out_trace())
        comp = [p for p in ctx.points if p.anomaly == "compression"]
        assert len(comp) == 0, f"False compression: {comp}"

    def test_no_anomalies_at_all(self):
        ctx = analyze_context_flow(_fan_out_trace())
        assert len(ctx.anomalies) == 0

    def test_size_mismatch_no_truncation(self):
        """Big agent → small agent size difference is NOT truncation."""
        ctx = analyze_context_flow(_fan_out_with_different_sizes())
        trunc = [p for p in ctx.points if p.anomaly == "truncation"]
        assert len(trunc) == 0

    def test_size_mismatch_no_anomalies(self):
        ctx = analyze_context_flow(_fan_out_with_different_sizes())
        assert len(ctx.anomalies) == 0

    def test_fan_out_handoff_count_zero(self):
        """Pure fan-out should have 0 inferred handoffs."""
        ctx = analyze_context_flow(_fan_out_trace())
        assert ctx.handoff_count == 0
