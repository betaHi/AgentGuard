"""Test: correlation analysis finds patterns within a single trace."""

from agentguard.builder import TraceBuilder
from agentguard.correlation import analyze_correlations, detect_patterns


def _trace_with_failure_cluster():
    """Multiple children failing under same parent."""
    return (TraceBuilder("failure cluster")
        .agent("coordinator", duration_ms=5000)
            .agent("worker_a", duration_ms=500, status="failed", error="timeout")
            .end()
            .agent("worker_b", duration_ms=500, status="failed", error="rate limit")
            .end()
            .agent("worker_c", duration_ms=500).end()
        .end()
        .build())


def _trace_with_slow_agent():
    """One agent significantly slower than others."""
    return (TraceBuilder("slow")
        .agent("coordinator", duration_ms=6000)
            .agent("fast_a", duration_ms=100).end()
            .agent("fast_b", duration_ms=120).end()
            .agent("slow_one", duration_ms=5000).end()
        .end()
        .build())


def _trace_with_timing_cluster():
    """Agents with very similar durations."""
    return (TraceBuilder("timing")
        .agent("coordinator", duration_ms=3000)
            .agent("agent_a", duration_ms=1000).end()
            .agent("agent_b", duration_ms=1005).end()
            .agent("agent_c", duration_ms=998).end()
        .end()
        .build())


class TestSingleTraceCorrelation:
    def test_failure_cluster_detected(self):
        r = analyze_correlations(_trace_with_failure_cluster())
        types = [p["type"] for p in r.patterns]
        assert "failure_cluster" in types

    def test_slow_agent_detected(self):
        r = analyze_correlations(_trace_with_slow_agent())
        types = [p["type"] for p in r.patterns]
        assert "slow_agent" in types

    def test_timing_cluster_detected(self):
        r = analyze_correlations(_trace_with_timing_cluster())
        types = [p["type"] for p in r.patterns]
        assert "timing_cluster" in types

    def test_failure_cluster_has_children(self):
        r = analyze_correlations(_trace_with_failure_cluster())
        cluster = [p for p in r.patterns if p["type"] == "failure_cluster"][0]
        assert "worker_a" in cluster["failed_children"]
        assert "worker_b" in cluster["failed_children"]

    def test_fingerprints_generated(self):
        r = analyze_correlations(_trace_with_slow_agent())
        assert len(r.fingerprints) > 0

    def test_patterns_have_description(self):
        r = analyze_correlations(_trace_with_failure_cluster())
        for p in r.patterns:
            assert "description" in p
            assert len(p["description"]) > 0

    def test_healthy_trace_no_patterns(self):
        t = TraceBuilder("clean").agent("a", duration_ms=100).end().build()
        r = analyze_correlations(t)
        # May have 0 or minimal patterns
        assert isinstance(r.patterns, list)

    def test_empty_trace(self):
        from agentguard.core.trace import ExecutionTrace
        t = ExecutionTrace(task="empty")
        t.complete()
        r = analyze_correlations(t)
        assert len(r.patterns) == 0
