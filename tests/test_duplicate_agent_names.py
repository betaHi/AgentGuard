"""Test: trace with duplicate agent names (same agent called multiple times).

Real-world traces often have the same agent invoked multiple times (retries,
loops, fan-out). Every module must handle this without crashes, incorrect
aggregation, or key collisions.
"""

import json

from agentguard.analysis import (
    analyze_bottleneck,
    analyze_context_flow,
    analyze_cost,
    analyze_cost_yield,
    analyze_decisions,
    analyze_failures,
    analyze_flow,
    analyze_timing,
)
from agentguard.builder import TraceBuilder
from agentguard.cli.main import _build_analysis_dict
from agentguard.normalize import normalize_trace
from agentguard.propagation import analyze_propagation
from agentguard.scoring import score_trace
from agentguard.summarize import summarize_trace
from agentguard.timeline import build_timeline
from agentguard.tree import compute_tree_stats, tree_to_text
from agentguard.web.viewer import trace_to_html_string


def _dup_trace():
    """Trace where 'researcher' is called 3 times under coordinator."""
    return (TraceBuilder("dup names test")
        .agent("coordinator", duration_ms=6000)
            .agent("researcher", duration_ms=1000,
                   input_data={"query": "first"},
                   output_data={"result": "r1"})
                .tool("search", duration_ms=500)
            .end()
            .agent("researcher", duration_ms=2000,
                   input_data={"query": "second"},
                   output_data={"result": "r2"})
                .tool("search", duration_ms=800)
            .end()
            .agent("researcher", duration_ms=500,
                   status="failed",
                   error="Timeout on third attempt")
                .tool("search", duration_ms=400)
            .end()
        .end()
        .build())


class TestDuplicateNamesAnalysis:
    def test_all_spans_present(self):
        t = _dup_trace()
        researchers = [s for s in t.agent_spans if s.name == "researcher"]
        assert len(researchers) == 3

    def test_analyze_failures(self):
        r = analyze_failures(_dup_trace())
        assert r.total_failed_spans >= 1

    def test_analyze_flow(self):
        r = analyze_flow(_dup_trace())
        assert r is not None

    def test_analyze_bottleneck(self):
        r = analyze_bottleneck(_dup_trace())
        assert r is not None

    def test_analyze_context_flow(self):
        r = analyze_context_flow(_dup_trace())
        assert r is not None

    def test_analyze_cost(self):
        r = analyze_cost(_dup_trace())
        assert r is not None

    def test_analyze_cost_yield(self):
        r = analyze_cost_yield(_dup_trace())
        assert r is not None

    def test_analyze_decisions(self):
        r = analyze_decisions(_dup_trace())
        assert r is not None

    def test_analyze_timing(self):
        r = analyze_timing(_dup_trace())
        assert r is not None

    def test_analyze_propagation(self):
        r = analyze_propagation(_dup_trace())
        assert r is not None

    def test_score(self):
        s = score_trace(_dup_trace())
        assert 0 <= s.overall <= 100


class TestDuplicateNamesViewer:
    def test_html_contains_all_instances(self):
        html = trace_to_html_string(_dup_trace())
        assert html.count("researcher") >= 3

    def test_html_valid(self):
        html = trace_to_html_string(_dup_trace())
        assert "<!DOCTYPE html>" in html


class TestDuplicateNamesSerialization:
    def test_json_round_trip(self):
        t = _dup_trace()
        j = t.to_json()
        parsed = json.loads(j)
        researchers = [s for s in parsed["spans"] if s["name"] == "researcher"]
        assert len(researchers) == 3

    def test_unique_span_ids(self):
        t = _dup_trace()
        ids = [s.span_id for s in t.spans]
        assert len(ids) == len(set(ids)), "Duplicate span_ids found"

    def test_cli_json(self):
        d = _build_analysis_dict(_dup_trace())
        assert d["trace"]["agent_count"] >= 3


class TestDuplicateNamesUtilities:
    def test_normalize(self):
        assert normalize_trace(_dup_trace()) is not None

    def test_summarize(self):
        assert summarize_trace(_dup_trace()) is not None

    def test_tree_text(self):
        txt = tree_to_text(_dup_trace())
        assert txt.count("researcher") >= 3

    def test_tree_stats(self):
        assert compute_tree_stats(_dup_trace()) is not None

    def test_timeline(self):
        assert build_timeline(_dup_trace()) is not None
