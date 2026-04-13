"""Tests for bottleneck agent ranking by own work time (Q1)."""

from agentguard.analysis import analyze_bottleneck
from agentguard.builder import TraceBuilder


class TestOwnTimeRanking:
    def test_own_time_excludes_children(self):
        """Own time = total - children durations."""
        trace = (TraceBuilder("own")
            .agent("parent", duration_ms=5000)
                .tool("child", duration_ms=4000)
            .end()
            .build())
        bn = analyze_bottleneck(trace)
        parent = [a for a in bn.agent_rankings if a["name"] == "parent"][0]
        assert parent["own_duration_ms"] == 1000
        assert parent["duration_ms"] == 5000

    def test_sorted_by_own_time(self):
        """Rankings sorted by own_duration_ms descending."""
        trace = (TraceBuilder("sort")
            .agent("busy", duration_ms=2000).end()  # 2000 own
            .agent("container", duration_ms=5000)    # 1000 own
                .tool("work", duration_ms=4000)
            .end()
            .build())
        bn = analyze_bottleneck(trace)
        names = [a["name"] for a in bn.agent_rankings]
        assert names[0] == "busy"  # 2000 own > 1000 own

    def test_own_pct_relative_to_total(self):
        """own_pct is relative to total trace duration."""
        trace = (TraceBuilder("pct")
            .agent("a", duration_ms=1000).end()
            .build())
        bn = analyze_bottleneck(trace)
        a = bn.agent_rankings[0]
        assert a["own_pct"] > 0
        assert a["own_pct"] <= 100

    def test_container_flagged(self):
        """Agents with children are flagged as containers."""
        trace = (TraceBuilder("flag")
            .agent("parent", duration_ms=3000)
                .agent("child", duration_ms=2000).end()
            .end()
            .build())
        bn = analyze_bottleneck(trace)
        parent = [a for a in bn.agent_rankings if a["name"] == "parent"][0]
        child = [a for a in bn.agent_rankings if a["name"] == "child"][0]
        assert parent["is_container"] is True
        assert child["is_container"] is False

    def test_report_shows_self_time(self):
        """to_report() displays self time for each agent."""
        trace = (TraceBuilder("report")
            .agent("worker", duration_ms=1000).end()
            .build())
        bn = analyze_bottleneck(trace)
        text = bn.to_report()
        assert "self:" in text

    def test_zero_own_time_when_all_in_children(self):
        """Agent with 100% time in children has 0 own time."""
        trace = (TraceBuilder("zero")
            .agent("wrapper", duration_ms=1000)
                .tool("real_work", duration_ms=1000)
            .end()
            .build())
        bn = analyze_bottleneck(trace)
        wrapper = [a for a in bn.agent_rankings if a["name"] == "wrapper"][0]
        assert wrapper["own_duration_ms"] == 0
