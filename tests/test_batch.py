"""Tests for batch processing."""

from agentguard.batch import batch_analyze
from agentguard.builder import TraceBuilder


def _traces(n=5):
    return [
        (TraceBuilder(f"trace_{i}")
            .agent("a", duration_ms=1000 * (i + 1), token_count=100 * (i + 1), cost_usd=0.01 * (i + 1))
            .end()
            .build())
        for i in range(n)
    ]


class TestBatchAnalyze:
    def test_basic(self):
        result = batch_analyze(_traces())
        assert result.trace_count == 5
        assert result.scores.count == 5

    def test_stats(self):
        result = batch_analyze(_traces())
        assert result.scores.mean > 0
        assert result.durations.mean > 0

    def test_tokens_cost(self):
        result = batch_analyze(_traces())
        assert result.total_tokens > 0
        assert result.total_cost_usd > 0

    def test_custom_analyzer(self):
        result = batch_analyze(
            _traces(),
            custom_analyzers={"span_count": lambda t: len(t.spans)},
        )
        assert "span_count" in result.custom_results
        assert len(result.custom_results["span_count"]) == 5

    def test_empty(self):
        result = batch_analyze([])
        assert result.trace_count == 0

    def test_report(self):
        result = batch_analyze(_traces())
        report = result.to_report()
        assert "Batch" in report

    def test_to_dict(self):
        result = batch_analyze(_traces())
        d = result.to_dict()
        assert "scores" in d
        assert "total_tokens" in d
