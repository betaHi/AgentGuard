"""Test: empty trace (0 spans) through the full analysis pipeline.

Every analysis function, scoring, viewer, CLI JSON, serialization,
and comparison must handle a trace with zero spans gracefully.
"""

import json
import pytest

from agentguard.core.trace import ExecutionTrace, SpanStatus
from agentguard.analysis import (
    analyze_failures, analyze_flow, analyze_bottleneck,
    analyze_context_flow, analyze_retries, analyze_cost,
    analyze_cost_yield, analyze_decisions, analyze_timing,
)
from agentguard.propagation import analyze_propagation
from agentguard.scoring import score_trace
from agentguard.web.viewer import trace_to_html_string
from agentguard.cli.main import _build_analysis_dict, _build_trace_metadata
from agentguard.normalize import normalize_trace
from agentguard.summarize import summarize_trace, summarize_brief
from agentguard.tree import tree_to_text, compute_tree_stats
from agentguard.timeline import build_timeline
from agentguard.filter import filter_spans


def _empty_trace():
    """Create a completed trace with zero spans."""
    t = ExecutionTrace(task="empty")
    t.complete()
    return t


class TestEmptyTraceAnalysis:
    """All analysis functions must handle 0-span traces."""

    def test_analyze_failures(self):
        r = analyze_failures(_empty_trace())
        assert r.total_failed_spans == 0

    def test_analyze_flow(self):
        r = analyze_flow(_empty_trace())
        assert r is not None

    def test_analyze_bottleneck(self):
        r = analyze_bottleneck(_empty_trace())
        assert r is not None

    def test_analyze_context_flow(self):
        r = analyze_context_flow(_empty_trace())
        assert r.handoff_count == 0

    def test_analyze_retries(self):
        r = analyze_retries(_empty_trace())
        assert r is not None

    def test_analyze_cost(self):
        r = analyze_cost(_empty_trace())
        assert r is not None

    def test_analyze_cost_yield(self):
        r = analyze_cost_yield(_empty_trace())
        assert r is not None

    def test_analyze_decisions(self):
        r = analyze_decisions(_empty_trace())
        assert r.total_decisions == 0

    def test_analyze_timing(self):
        r = analyze_timing(_empty_trace())
        assert r is not None

    def test_analyze_propagation(self):
        r = analyze_propagation(_empty_trace())
        assert r.total_failures == 0


class TestEmptyTraceScoring:
    def test_score(self):
        s = score_trace(_empty_trace())
        assert 0 <= s.overall <= 100
        assert s.grade in ("A", "B", "C", "D", "F")


class TestEmptyTraceViewer:
    def test_html_output(self):
        html = trace_to_html_string(_empty_trace())
        assert "<!DOCTYPE html>" in html
        assert len(html) > 100


class TestEmptyTraceCLI:
    def test_build_analysis_dict(self):
        d = _build_analysis_dict(_empty_trace())
        assert "trace" in d
        assert d["trace"]["span_count"] == 0

    def test_build_trace_metadata(self):
        m = _build_trace_metadata(_empty_trace())
        assert m["agent_count"] == 0
        assert m["span_count"] == 0
        assert m["task"] == "empty"


class TestEmptyTraceSerialization:
    def test_to_dict(self):
        d = _empty_trace().to_dict()
        assert d["spans"] == []

    def test_to_json(self):
        j = _empty_trace().to_json()
        parsed = json.loads(j)
        assert parsed["spans"] == []

    def test_to_json_truncate(self):
        j = _empty_trace().to_json(truncate=True)
        assert json.loads(j)["spans"] == []


class TestEmptyTraceUtilities:
    def test_normalize(self):
        r = normalize_trace(_empty_trace())
        assert r is not None

    def test_summarize(self):
        r = summarize_trace(_empty_trace())
        assert r is not None

    def test_summarize_brief(self):
        r = summarize_brief(_empty_trace())
        assert isinstance(r, str)

    def test_tree_to_text(self):
        r = tree_to_text(_empty_trace())
        assert isinstance(r, str)

    def test_compute_tree_stats(self):
        r = compute_tree_stats(_empty_trace())
        assert r is not None

    def test_build_timeline(self):
        r = build_timeline(_empty_trace())
        assert r is not None

    def test_filter_spans(self):
        r = filter_spans(_empty_trace())
        assert r == []
