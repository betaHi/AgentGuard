"""Tests for ASCII visualization."""

import pytest
from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace, SpanStatus
from agentguard.ascii_viz import gantt_chart, status_summary, span_distribution


@pytest.fixture
def trace():
    return (TraceBuilder("viz_test")
        .agent("researcher", duration_ms=3000)
            .tool("web_search", duration_ms=1000)
        .end()
        .agent("writer", duration_ms=5000, status="failed", error="timeout")
        .end()
        .build())


class TestGantt:
    def test_basic(self, trace):
        chart = gantt_chart(trace)
        assert "researcher" in chart
        assert "writer" in chart
        assert "█" in chart or "▓" in chart

    def test_empty(self):
        assert "no timed" in gantt_chart(ExecutionTrace())


class TestStatusSummary:
    def test_basic(self, trace):
        summary = status_summary(trace)
        assert "viz_test" in summary
        assert "🟢" in summary or "🔴" in summary

    def test_all_good(self):
        t = (TraceBuilder("good")
            .agent("a").end()
            .agent("b").end()
            .build())
        summary = status_summary(t)
        assert "✅" in summary


class TestDistribution:
    def test_basic(self, trace):
        dist = span_distribution(trace)
        assert "agent" in dist
        assert "tool" in dist
        assert "completed" in dist or "failed" in dist
