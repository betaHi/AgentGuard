"""Tests for Q4 custom cost models in cost-yield analysis."""

from agentguard.analysis import analyze_cost_yield
from agentguard.builder import TraceBuilder


def _trace():
    return (TraceBuilder("custom cost")
        .agent("fast_agent", duration_ms=100, token_count=10, cost_usd=0.001)
        .end()
        .agent("slow_agent", duration_ms=5000, token_count=100, cost_usd=0.01)
        .end()
        .build())


class TestCustomCostFn:
    def test_default_uses_estimated_cost(self):
        r = analyze_cost_yield(_trace())
        assert r.total_cost_usd > 0

    def test_custom_cost_fn_duration_based(self):
        """Cost = duration in seconds."""
        r = analyze_cost_yield(_trace(), cost_fn=lambda s: (s.duration_ms or 0) / 1000)
        slow = [e for e in r.entries if e.agent == "slow_agent"][0]
        assert slow.cost_usd == 5.0

    def test_custom_cost_fn_flat_rate(self):
        r = analyze_cost_yield(_trace(), cost_fn=lambda s: 1.0)
        assert r.total_cost_usd == 2.0

    def test_custom_cost_fn_zero(self):
        r = analyze_cost_yield(_trace(), cost_fn=lambda s: 0.0)
        assert r.total_cost_usd == 0.0

    def test_custom_cost_changes_wasteful(self):
        """With duration-based cost, slow_agent becomes most wasteful."""
        r = analyze_cost_yield(_trace(), cost_fn=lambda s: (s.duration_ms or 0) / 1000)
        # slow_agent costs 5.0 vs fast_agent 0.1
        assert r.highest_cost_agent == "slow_agent"


class TestCustomYieldFn:
    def test_default_yield_scoring(self):
        r = analyze_cost_yield(_trace())
        for e in r.entries:
            assert 0 <= e.yield_score <= 100

    def test_custom_yield_fn(self):
        """Yield = token count (custom metric)."""
        r = analyze_cost_yield(_trace(), yield_fn=lambda s: float(s.token_count or 0))
        fast = [e for e in r.entries if e.agent == "fast_agent"][0]
        assert fast.yield_score == 10.0

    def test_custom_both_fns(self):
        """Both cost and yield are custom."""
        r = analyze_cost_yield(
            _trace(),
            cost_fn=lambda s: (s.duration_ms or 0) / 1000,
            yield_fn=lambda s: 100.0 if s.token_count and s.token_count > 50 else 0.0,
        )
        slow = [e for e in r.entries if e.agent == "slow_agent"][0]
        assert slow.cost_usd == 5.0
        assert slow.yield_score == 100.0

    def test_none_fns_uses_defaults(self):
        r1 = analyze_cost_yield(_trace())
        r2 = analyze_cost_yield(_trace(), cost_fn=None, yield_fn=None)
        assert r1.total_cost_usd == r2.total_cost_usd
