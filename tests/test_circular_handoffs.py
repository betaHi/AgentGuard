"""Test: trace with circular handoffs (A→B→A).

Circular delegation patterns are common in debate/review architectures.
No module should infinite-loop or crash on cycles.
"""

import json
from agentguard.builder import TraceBuilder
from agentguard.analysis import (
    analyze_failures, analyze_flow, analyze_bottleneck,
    analyze_context_flow, analyze_cost_yield, analyze_decisions,
)
from agentguard.propagation import analyze_propagation
from agentguard.scoring import score_trace
from agentguard.web.viewer import trace_to_html_string
from agentguard.cli.main import _build_analysis_dict
from agentguard.tree import tree_to_text
from agentguard.timeline import build_timeline


def _circular_trace():
    """A→B→A circular handoff pattern (debate/review)."""
    return (TraceBuilder("circular handoff test")
        .agent("coordinator", duration_ms=8000)
            .agent("agent_a", duration_ms=2000,
                   output_data={"draft": "v1"})
            .end()
            .handoff("agent_a", "agent_b",
                     context_size=100)
            .agent("agent_b", duration_ms=2000,
                   input_data={"draft": "v1"},
                   output_data={"review": "needs changes"})
            .end()
            .handoff("agent_b", "agent_a",
                     context_size=150)
            .agent("agent_a", duration_ms=1500,
                   input_data={"review": "needs changes"},
                   output_data={"draft": "v2"})
            .end()
        .end()
        .build())


class TestCircularHandoffs:
    def test_handoff_count(self):
        t = _circular_trace()
        handoffs = [s for s in t.spans if s.span_type.value == "handoff"]
        assert len(handoffs) == 2

    def test_analyze_flow_no_infinite_loop(self):
        r = analyze_flow(_circular_trace())
        assert r is not None

    def test_analyze_context_flow(self):
        r = analyze_context_flow(_circular_trace())
        assert r.handoff_count >= 1

    def test_analyze_bottleneck(self):
        r = analyze_bottleneck(_circular_trace())
        assert r is not None

    def test_analyze_failures(self):
        r = analyze_failures(_circular_trace())
        assert r.total_failed_spans == 0

    def test_analyze_cost_yield(self):
        assert analyze_cost_yield(_circular_trace()) is not None

    def test_analyze_decisions(self):
        assert analyze_decisions(_circular_trace()) is not None

    def test_analyze_propagation(self):
        assert analyze_propagation(_circular_trace()) is not None

    def test_score(self):
        s = score_trace(_circular_trace())
        assert 0 <= s.overall <= 100

    def test_html_viewer(self):
        html = trace_to_html_string(_circular_trace())
        assert "agent_a" in html
        assert "agent_b" in html

    def test_cli_json(self):
        d = _build_analysis_dict(_circular_trace())
        assert d["trace"]["handoff_count"] == 2

    def test_tree_text(self):
        txt = tree_to_text(_circular_trace())
        assert "agent_a" in txt

    def test_timeline(self):
        assert build_timeline(_circular_trace()) is not None

    def test_json_round_trip(self):
        j = _circular_trace().to_json()
        parsed = json.loads(j)
        names = [s["name"] for s in parsed["spans"]]
        assert names.count("agent_a") == 2

    def test_unique_span_ids(self):
        ids = [s.span_id for s in _circular_trace().spans]
        assert len(ids) == len(set(ids))
