"""Test: TraceBuilder with duration_ms produces spans with correct timestamps."""

from datetime import datetime, timezone
from agentguard.builder import TraceBuilder


class TestBuilderTimestamps:
    def test_span_has_started_at(self):
        t = TraceBuilder("t").agent("a", duration_ms=1000).end().build()
        assert t.spans[0].started_at is not None
        assert len(t.spans[0].started_at) > 10

    def test_span_has_ended_at(self):
        t = TraceBuilder("t").agent("a", duration_ms=1000).end().build()
        assert t.spans[0].ended_at is not None

    def test_duration_ms_correct(self):
        t = TraceBuilder("t").agent("a", duration_ms=3000).end().build()
        assert abs(t.spans[0].duration_ms - 3000) < 1

    def test_sequential_spans_non_overlapping(self):
        """Second span starts after first ends."""
        t = (TraceBuilder("t")
            .agent("a", duration_ms=1000).end()
            .agent("b", duration_ms=2000).end()
            .build())
        a_end = datetime.fromisoformat(t.spans[0].ended_at)
        b_start = datetime.fromisoformat(t.spans[1].started_at)
        assert b_start >= a_end

    def test_child_starts_at_parent_start(self):
        """First child starts at or after parent start."""
        t = (TraceBuilder("t")
            .agent("parent", duration_ms=5000)
                .agent("child", duration_ms=1000).end()
            .end()
            .build())
        parent = [s for s in t.spans if s.name == "parent"][0]
        child = [s for s in t.spans if s.name == "child"][0]
        p_start = datetime.fromisoformat(parent.started_at)
        c_start = datetime.fromisoformat(child.started_at)
        assert c_start >= p_start

    def test_tool_duration(self):
        t = TraceBuilder("t").agent("a", duration_ms=2000).tool("t", duration_ms=500).end().build()
        tool = [s for s in t.spans if s.name == "t"][0]
        assert abs(tool.duration_ms - 500) < 1

    def test_trace_duration_covers_all_spans(self):
        t = (TraceBuilder("t")
            .agent("a", duration_ms=1000).end()
            .agent("b", duration_ms=2000).end()
            .build())
        assert t.duration_ms >= 3000

    def test_zero_duration_valid(self):
        t = TraceBuilder("t").agent("a", duration_ms=0).end().build()
        assert t.spans[0].duration_ms == 0
        assert t.spans[0].started_at == t.spans[0].ended_at

    def test_large_duration(self):
        t = TraceBuilder("t").agent("a", duration_ms=60000).end().build()
        assert abs(t.spans[0].duration_ms - 60000) < 1

    def test_timestamps_are_iso_format(self):
        t = TraceBuilder("t").agent("a", duration_ms=100).end().build()
        # Should parse without error
        datetime.fromisoformat(t.spans[0].started_at)
        datetime.fromisoformat(t.spans[0].ended_at)
