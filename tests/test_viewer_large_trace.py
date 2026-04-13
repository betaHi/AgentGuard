"""Test: HTML viewer renders correctly with 50+ agent traces.

Ensures the viewer doesn't crash, produce invalid HTML, or become
unreasonably large with many agents.
"""

from agentguard.builder import TraceBuilder
from agentguard.web.viewer import trace_to_html_string


def _large_trace(n_agents=50):
    """Build a trace with N agents under a coordinator."""
    b = TraceBuilder(f"large trace ({n_agents} agents)")
    b = b.agent("coordinator", duration_ms=n_agents * 200)
    for i in range(n_agents):
        status = "failed" if i % 10 == 9 else "completed"
        error = f"error_{i}" if status == "failed" else None
        b = b.agent(f"agent_{i:03d}", duration_ms=100 + i * 10,
                    token_count=i * 50, cost_usd=i * 0.001,
                    status=status, error=error)
        b = b.tool(f"tool_{i:03d}", duration_ms=50 + i * 5)
        b = b.end()  # agent
    b = b.end()  # coordinator
    return b.build()


class TestLargeTraceViewer:
    def test_50_agents_renders(self):
        html = trace_to_html_string(_large_trace(50))
        assert "<!DOCTYPE html>" in html
        assert "agent_049" in html

    def test_100_agents_renders(self):
        html = trace_to_html_string(_large_trace(100))
        assert "agent_099" in html

    def test_all_agents_present(self):
        html = trace_to_html_string(_large_trace(50))
        for i in range(50):
            assert f"agent_{i:03d}" in html

    def test_failed_agents_shown(self):
        html = trace_to_html_string(_large_trace(50))
        assert "agent_009" in html  # first failed (i%10==9)
        assert "err" in html.lower() or "failed" in html.lower()

    def test_html_size_reasonable(self):
        """50-agent HTML should be under 1MB."""
        html = trace_to_html_string(_large_trace(50))
        assert len(html.encode()) < 1_000_000

    def test_diagnostics_present(self):
        html = trace_to_html_string(_large_trace(50))
        assert "Bottleneck" in html
        assert "Cost" in html

    def test_search_filter_present(self):
        html = trace_to_html_string(_large_trace(50))
        assert "span-search" in html
