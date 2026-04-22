"""Q2 critical-key provenance: users must be able to see *why* a key was flagged."""

from __future__ import annotations

from agentguard.analysis import (
    _infer_critical_keys_with_provenance,
    _LEARNED_KEYS_STATE,
    analyze_context_flow,
)
from agentguard.builder import TraceBuilder
from agentguard.web.viewer import _render_context_flow_panel


def test_explicit_keys_have_explicit_provenance():
    keys, source = _infer_critical_keys_with_provenance(
        {"a": 1, "b": 2, "whatever": 3}, explicit_keys=["a", "b"],
    )
    assert keys == ["a", "b"]
    assert source == "explicit"


def test_heuristic_source_when_name_matches_keyword():
    keys, source = _infer_critical_keys_with_provenance(
        {"query": "hi", "unrelated": "x"},
    )
    assert "query" in keys
    assert source == "heuristic"


def test_learned_source_beats_heuristic(monkeypatch):
    monkeypatch.setitem(_LEARNED_KEYS_STATE, "keys", frozenset({"doc_ids"}))
    try:
        keys, source = _infer_critical_keys_with_provenance(
            {"doc_ids": [1, 2], "other": "x"},
        )
        assert "doc_ids" in keys
        assert source == "learned"
    finally:
        _LEARNED_KEYS_STATE.pop("keys", None)


def test_no_keys_no_source():
    keys, source = _infer_critical_keys_with_provenance({"foo": 1})
    assert keys == []
    assert source == ""


def test_flow_point_carries_provenance_through_analysis():
    trace = (
        TraceBuilder("q2-provenance")
        .agent("coordinator", duration_ms=500)
            .agent("planner", duration_ms=100,
                   output_data={
                       "task": "research",
                       "doc_ids": ["d1", "d2"],
                       "requirements": ["tone"],
                   })
            .end()
            .agent("researcher", duration_ms=200,
                   input_data={"task": "research"})
            .end()
        .end()
        .build()
    )
    flow = analyze_context_flow(trace)
    assert flow.points
    sources = {p.critical_key_source for p in flow.points}
    # At minimum one of the inferred handoffs must have declared provenance.
    assert sources & {"heuristic", "learned"}, sources


def test_viewer_renders_why_flagged_block():
    trace = (
        TraceBuilder("q2-provenance-html")
        .agent("coordinator", duration_ms=500)
            .agent("planner", duration_ms=100,
                   output_data={
                       "task": "summarise",
                       "query": "x",
                       "requirements": ["y"],
                   })
            .end()
            .agent("researcher", duration_ms=200,
                   input_data={"task": "summarise"})  # drops query + requirements
            .end()
        .end()
        .build()
    )
    flow = analyze_context_flow(trace)
    html = _render_context_flow_panel(flow)
    assert "why flagged" in html, html
