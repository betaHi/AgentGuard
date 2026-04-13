"""Tests for Q3 recoverable vs fatal failure classification."""

from agentguard.builder import TraceBuilder
from agentguard.propagation import analyze_propagation


def _contained_failure_trace():
    """Failure contained by circuit breaker → recoverable."""
    return (TraceBuilder("contained")
        .agent("coordinator", duration_ms=5000)
            .agent("worker", duration_ms=1000,
                   status="failed", error="timeout")
            .end()
            .agent("fallback", duration_ms=500)
            .end()
        .end()
        .build())


def _fatal_cascade_trace():
    """Deep failure cascade, trace fails → fatal."""
    return (TraceBuilder("fatal cascade")
        .agent("coordinator", duration_ms=5000,
               status="failed", error="cascade")
            .agent("middle", duration_ms=3000,
                   status="failed", error="propagated")
                .agent("root_cause", duration_ms=1000,
                       status="failed", error="db connection refused")
                .end()
            .end()
        .end()
        .build())


def _shallow_failure_trace():
    """Single shallow failure, trace succeeds → recoverable."""
    return (TraceBuilder("shallow")
        .agent("coordinator", duration_ms=3000)
            .agent("worker", duration_ms=500,
                   status="failed", error="minor error")
            .end()
            .agent("backup", duration_ms=500)
            .end()
        .end()
        .build())


class TestFailureSeverity:
    def test_contained_is_recoverable(self):
        r = analyze_propagation(_contained_failure_trace())
        if r.causal_chains:
            assert r.causal_chains[0].severity == "recoverable"

    def test_deep_cascade_is_fatal(self):
        r = analyze_propagation(_fatal_cascade_trace())
        fatals = [c for c in r.causal_chains if c.severity == "fatal"]
        assert len(fatals) > 0

    def test_shallow_is_recoverable(self):
        r = analyze_propagation(_shallow_failure_trace())
        for chain in r.causal_chains:
            assert chain.severity == "recoverable"

    def test_severity_in_dict(self):
        r = analyze_propagation(_fatal_cascade_trace())
        if r.causal_chains:
            d = r.causal_chains[0].to_dict()
            assert "severity" in d
            assert "severity_reason" in d

    def test_severity_reason_not_empty(self):
        r = analyze_propagation(_fatal_cascade_trace())
        for chain in r.causal_chains:
            assert chain.severity_reason != ""

    def test_no_failures_no_chains(self):
        t = TraceBuilder("ok").agent("a", duration_ms=100).end().build()
        r = analyze_propagation(t)
        assert len(r.causal_chains) == 0

    def test_empty_trace(self):
        from agentguard.core.trace import ExecutionTrace
        t = ExecutionTrace(task="empty")
        t.complete()
        r = analyze_propagation(t)
        assert r.total_failures == 0
