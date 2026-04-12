"""Tests for trace comparison viewer."""

from agentguard.ascii_viz import compare_view
from agentguard.builder import TraceBuilder


def _trace(name, agents):
    b = TraceBuilder(name)
    for a_name, dur in agents:
        b.agent(a_name, duration_ms=dur).end()
    return b.build()


class TestCompareView:
    def test_identical_traces_no_diffs(self):
        a = _trace("a", [("planner", 100), ("writer", 200)])
        b = _trace("b", [("planner", 100), ("writer", 200)])
        text = compare_view(a, b)
        assert "0 changed" in text

    def test_timing_difference_highlighted(self):
        a = _trace("a", [("slow", 1000)])
        b = _trace("b", [("slow", 500)])
        text = compare_view(a, b)
        assert "timing:" in text

    def test_added_agent_shown(self):
        a = _trace("a", [("planner", 100)])
        b = _trace("b", [("planner", 100), ("reviewer", 200)])
        text = compare_view(a, b)
        assert "(absent)" in text
        assert "1 added" in text

    def test_removed_agent_shown(self):
        a = _trace("a", [("planner", 100), ("old", 50)])
        b = _trace("b", [("planner", 100)])
        text = compare_view(a, b)
        assert "1 removed" in text

    def test_custom_labels(self):
        a = _trace("a", [("x", 100)])
        b = _trace("b", [("x", 100)])
        text = compare_view(a, b, label_a="v1.0", label_b="v2.0")
        assert "v1.0" in text
        assert "v2.0" in text

    def test_empty_traces(self):
        a = _trace("a", [])
        b = _trace("b", [])
        text = compare_view(a, b)
        assert "0 agents" in text

    def test_status_icons_present(self):
        a = _trace("a", [("agent", 100)])
        b = _trace("b", [("agent", 100)])
        text = compare_view(a, b)
        assert "✓" in text
