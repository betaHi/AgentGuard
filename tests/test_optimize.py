"""Tests for trace optimization suggestions."""

import pytest
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.builder import TraceBuilder
from agentguard.optimize import suggest_optimizations


class TestOptimizations:
    def test_retry_detection(self):
        trace = (TraceBuilder("retry")
            .agent("orchestrator")
                .tool("flaky_api", retry_count=5)
            .end()
            .build())
        result = suggest_optimizations(trace)
        retry_suggestions = [s for s in result.suggestions if "retry" in s.title.lower()]
        assert len(retry_suggestions) >= 1

    def test_cost_dominant_span(self):
        trace = (TraceBuilder("cost")
            .agent("cheap", cost_usd=0.01, token_count=100).end()
            .agent("expensive", cost_usd=10.0, token_count=100000).end()
            .build())
        result = suggest_optimizations(trace)
        cost_suggestions = [s for s in result.suggestions if s.category == "cost"]
        assert len(cost_suggestions) >= 1

    def test_clean_trace(self):
        trace = (TraceBuilder("clean")
            .agent("a", duration_ms=1000).end()
            .build())
        result = suggest_optimizations(trace)
        assert isinstance(result.suggestions, list)

    def test_report(self):
        trace = (TraceBuilder("report")
            .agent("a").tool("slow_tool", duration_ms=10000).end()
            .build())
        result = suggest_optimizations(trace)
        report = result.to_report()
        assert "Optimization" in report

    def test_to_dict(self):
        trace = (TraceBuilder("dict")
            .agent("a").end()
            .build())
        result = suggest_optimizations(trace)
        d = result.to_dict()
        assert "suggestions" in d
        assert "estimated_savings_pct" in d
