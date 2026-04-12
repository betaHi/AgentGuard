"""Tests for trace search."""

import pytest
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.search import search_traces


def _make_traces():
    t1 = ExecutionTrace(trace_id="t1", task="pipeline_1")
    t1.add_span(Span(name="researcher", error=None, tags=["critical"]))
    t1.add_span(Span(name="web_search", span_type=SpanType.TOOL, error="timeout"))
    
    t2 = ExecutionTrace(trace_id="t2", task="pipeline_2")
    t2.add_span(Span(name="writer", tags=["experimental"]))
    t2.add_span(Span(name="api_call", span_type=SpanType.TOOL,
                    metadata={"model": "gpt-4", "provider": "openai"}))
    
    return [t1, t2]


class TestSearchTraces:
    def test_search_by_name(self):
        result = search_traces(_make_traces(), "researcher")
        assert len(result.hits) == 1
        assert result.hits[0].span_name == "researcher"

    def test_search_by_error(self):
        result = search_traces(_make_traces(), "timeout")
        assert len(result.hits) == 1
        assert result.hits[0].match_field == "error"

    def test_search_by_tag(self):
        result = search_traces(_make_traces(), "critical")
        assert len(result.hits) == 1

    def test_search_by_metadata(self):
        result = search_traces(_make_traces(), "gpt-4")
        assert len(result.hits) >= 1

    def test_regex_search(self):
        result = search_traces(_make_traces(), r"web_\w+")
        assert len(result.hits) >= 1

    def test_case_insensitive(self):
        result = search_traces(_make_traces(), "RESEARCHER")
        assert len(result.hits) == 1

    def test_no_results(self):
        result = search_traces(_make_traces(), "nonexistent_xyz")
        assert len(result.hits) == 0

    def test_report(self):
        result = search_traces(_make_traces(), "search")
        report = result.to_report()
        assert "Search" in report

    def test_to_dict(self):
        result = search_traces(_make_traces(), "researcher")
        d = result.to_dict()
        assert "hits" in d
        assert d["hit_count"] == 1
