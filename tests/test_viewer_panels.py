"""Tests for HTML viewer diagnostics panel completeness."""

from agentguard.web.viewer import trace_to_html_string
from agentguard.builder import TraceBuilder


def _sample_trace():
    return (TraceBuilder("viewer")
        .agent("coordinator", duration_ms=5000)
            .agent("researcher", duration_ms=3000)
                .tool("search", duration_ms=2000)
            .end()
            .agent("writer", duration_ms=1000).end()
        .end()
        .build())


class TestViewerPanels:
    def test_all_panels_present(self):
        """All analysis panels render in HTML output."""
        html = trace_to_html_string(_sample_trace())
        panels = [
            "Failure Propagation", "Bottleneck", "Handoff Flow",
            "Critical Path", "Cost", "Retries", "Error Classification",
            "Cost-Yield", "Orchestration Decisions",
        ]
        for panel in panels:
            assert panel in html, f"Panel '{panel}' missing from HTML"

    def test_cost_yield_panel_content(self):
        html = trace_to_html_string(_sample_trace())
        assert "waste" in html.lower() or "No waste" in html

    def test_decisions_panel_content(self):
        html = trace_to_html_string(_sample_trace())
        assert "quality" in html.lower() or "No decisions" in html

    def test_propagation_panel_content(self):
        html = trace_to_html_string(_sample_trace())
        assert "containment" in html.lower() or "No propagation" in html

    def test_empty_trace_no_crash(self):
        """Empty trace produces valid HTML."""
        from agentguard.core.trace import ExecutionTrace
        trace = ExecutionTrace(task="empty")
        trace.complete()
        html = trace_to_html_string(trace)
        assert "<!DOCTYPE html>" in html

    def test_html_is_valid_string(self):
        html = trace_to_html_string(_sample_trace())
        assert isinstance(html, str)
        assert len(html) > 1000


class TestTraceMetadataHeader:
    def test_task_name_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "viewer" in html  # task name

    def test_agent_count_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "agents" in html

    def test_span_count_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "spans" in html

    def test_duration_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "total" in html

    def test_failed_count_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "failed" in html

    def test_tools_count_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "tools" in html
