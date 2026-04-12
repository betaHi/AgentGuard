"""Tests for dashboard data."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.builder import TraceBuilder
from agentguard.dashboard import build_dashboard


def _good_trace(i=0):
    return (TraceBuilder(f"good_{i}")
        .agent("a", duration_ms=3000, token_count=1000, cost_usd=0.03).end()
        .build())


def _bad_trace(i=0):
    return (TraceBuilder(f"bad_{i}")
        .agent("a", duration_ms=10000, status="failed", error="crash").end()
        .build())


class TestDashboard:
    def test_healthy(self):
        traces = [_good_trace(i) for i in range(5)]
        data = build_dashboard(traces)
        assert data.health_status == "healthy"
        assert data.trace_count == 5

    def test_degraded(self):
        traces = [_good_trace(0), _good_trace(1), _good_trace(2), _bad_trace(3)]
        data = build_dashboard(traces)
        assert data.health_status in ("healthy", "degraded", "critical")

    def test_critical(self):
        traces = [_bad_trace(i) for i in range(5)]
        data = build_dashboard(traces)
        assert data.health_status == "critical"

    def test_empty(self):
        data = build_dashboard([])
        assert data.health_status == "unknown"
        assert data.trace_count == 0

    def test_recent_traces(self):
        traces = [_good_trace(i) for i in range(3)]
        data = build_dashboard(traces)
        assert len(data.recent_traces) == 3

    def test_to_dict(self):
        data = build_dashboard([_good_trace()])
        d = data.to_dict()
        assert "health" in d
        assert "score" in d
        assert "trend" in d
