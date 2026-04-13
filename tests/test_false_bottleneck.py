"""Tests for Q1 false bottleneck detection.

A false bottleneck is an agent that appears slow (high wall time) but
is actually just waiting on its children (low own work time).
"""

from agentguard.analysis import analyze_bottleneck
from agentguard.builder import TraceBuilder


def _false_bottleneck_trace():
    """Coordinator has 10s wall time but only 200ms own work."""
    return (TraceBuilder("false bottleneck test")
        .agent("coordinator", duration_ms=10000)
            .agent("slow_worker", duration_ms=8000)
                .tool("database_query", duration_ms=7500)
            .end()
            .agent("fast_worker", duration_ms=1000)
            .end()
        .end()
        .build())


def _real_bottleneck_trace():
    """Agent does all work itself — no false bottleneck."""
    return (TraceBuilder("real bottleneck test")
        .agent("worker_a", duration_ms=5000)
            .tool("quick_call", duration_ms=100)
        .end()
        .agent("worker_b", duration_ms=1000)
        .end()
        .build())


def _no_container_trace():
    """Flat trace with no nesting — no false bottleneck possible."""
    return (TraceBuilder("flat test")
        .agent("a", duration_ms=3000).end()
        .agent("b", duration_ms=1000).end()
        .build())


class TestFalseBottleneck:
    def test_detects_false_bottleneck(self):
        """Coordinator is flagged as false bottleneck."""
        r = analyze_bottleneck(_false_bottleneck_trace())
        assert r.false_bottleneck == "coordinator"
        assert "coordinator" in r.false_bottleneck_detail
        assert "own work" in r.false_bottleneck_detail

    def test_real_bottleneck_not_flagged(self):
        """Agent doing real work is NOT a false bottleneck."""
        r = analyze_bottleneck(_real_bottleneck_trace())
        assert r.false_bottleneck is None

    def test_flat_trace_no_false_bottleneck(self):
        r = analyze_bottleneck(_no_container_trace())
        assert r.false_bottleneck is None

    def test_false_bottleneck_in_dict(self):
        d = analyze_bottleneck(_false_bottleneck_trace()).to_dict()
        assert d["false_bottleneck"] == "coordinator"
        assert len(d["false_bottleneck_detail"]) > 0

    def test_no_false_bottleneck_in_dict(self):
        d = analyze_bottleneck(_real_bottleneck_trace()).to_dict()
        assert d["false_bottleneck"] is None

    def test_detail_mentions_dependency_wait(self):
        r = analyze_bottleneck(_false_bottleneck_trace())
        assert "dependency wait" in r.false_bottleneck_detail.lower() or \
               "dependency" in r.false_bottleneck_detail.lower()

    def test_detail_suggests_optimizing_children(self):
        r = analyze_bottleneck(_false_bottleneck_trace())
        assert "children" in r.false_bottleneck_detail.lower() or \
               "optimize" in r.false_bottleneck_detail.lower()

    def test_empty_trace(self):
        from agentguard.core.trace import ExecutionTrace
        t = ExecutionTrace(task="empty")
        t.complete()
        r = analyze_bottleneck(t)
        assert r.false_bottleneck is None
