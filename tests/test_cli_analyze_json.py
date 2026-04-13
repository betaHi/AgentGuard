"""Tests for CLI analyze --json structured output."""

import json
from agentguard.cli.main import _build_analysis_dict, _build_trace_metadata
from agentguard.builder import TraceBuilder


def _sample_trace():
    return (TraceBuilder("cli test")
        .agent("researcher", duration_ms=3000)
            .tool("search", duration_ms=2000)
        .end()
        .agent("writer", duration_ms=1000).end()
        .build())


class TestAnalyzeJson:
    def test_all_sections_present(self):
        """JSON output includes all analysis sections."""
        result = _build_analysis_dict(_sample_trace())
        required = ["trace", "score", "failures", "flow", "bottleneck",
                     "context_flow", "cost_yield", "decisions", "propagation"]
        for key in required:
            assert key in result, f"Missing section: {key}"

    def test_trace_metadata(self):
        result = _build_analysis_dict(_sample_trace())
        meta = result["trace"]
        assert meta["task"] == "cli test"
        assert meta["agent_count"] == 2
        assert meta["span_count"] >= 3
        assert "tool_count" in meta
        assert "failed_count" in meta

    def test_json_serializable(self):
        """Full output is JSON-serializable."""
        result = _build_analysis_dict(_sample_trace())
        serialized = json.dumps(result, default=str)
        parsed = json.loads(serialized)
        assert "trace" in parsed

    def test_score_present(self):
        result = _build_analysis_dict(_sample_trace())
        assert "overall" in result["score"]
        assert "grade" in result["score"]

    def test_build_trace_metadata_counts(self):
        trace = _sample_trace()
        meta = _build_trace_metadata(trace)
        assert meta["agent_count"] == 2
        assert meta["tool_count"] == 1
        assert meta["handoff_count"] == 0

    def test_matches_viewer_sections(self):
        """JSON sections match what the HTML viewer renders."""
        result = _build_analysis_dict(_sample_trace())
        # Viewer renders: failures, bottleneck, flow, context_flow,
        # cost_yield, decisions, propagation
        viewer_sections = ["failures", "bottleneck", "flow",
                           "context_flow", "cost_yield", "decisions",
                           "propagation"]
        for section in viewer_sections:
            assert section in result
