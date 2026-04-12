"""Tests for agent drill-down viewer."""

from agentguard.ascii_viz import agent_drill_down
from agentguard.builder import TraceBuilder


def _trace_with_tools():
    return (TraceBuilder("drill")
        .agent("researcher", duration_ms=3000)
            .tool("web_search", duration_ms=1500)
            .tool("db_query", duration_ms=800)
        .end()
        .agent("writer", duration_ms=500).end()
        .build())


class TestAgentDrillDown:
    def test_shows_child_tools(self):
        text = agent_drill_down(_trace_with_tools(), "researcher")
        assert "web_search" in text
        assert "db_query" in text

    def test_shows_self_time(self):
        text = agent_drill_down(_trace_with_tools(), "researcher")
        assert "(self-time)" in text
        assert "700ms" in text  # 3000 - 1500 - 800

    def test_sorted_by_duration(self):
        text = agent_drill_down(_trace_with_tools(), "researcher")
        ws_pos = text.index("web_search")
        db_pos = text.index("db_query")
        assert ws_pos < db_pos  # slower first

    def test_agent_not_found(self):
        text = agent_drill_down(_trace_with_tools(), "ghost")
        assert "not found" in text

    def test_agent_no_children(self):
        text = agent_drill_down(_trace_with_tools(), "writer")
        assert "Children: 0" in text
        assert "(self-time)" in text

    def test_percentages_shown(self):
        text = agent_drill_down(_trace_with_tools(), "researcher")
        assert "50.0%" in text  # web_search = 1500/3000

    def test_bar_chars_present(self):
        text = agent_drill_down(_trace_with_tools(), "researcher")
        assert "█" in text  # completed bars
        assert "░" in text  # self-time
