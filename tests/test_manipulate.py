"""Tests for trace manipulation."""

import pytest

from agentguard.builder import TraceBuilder
from agentguard.core.trace import SpanStatus, SpanType
from agentguard.manipulate import anonymize_trace, clone_trace, merge_traces, slice_trace


@pytest.fixture
def trace():
    return (TraceBuilder("manipulation_test")
        .agent("researcher", duration_ms=3000, output_data={"articles": [1, 2], "secret": "api_key_123"})
            .tool("web_search", duration_ms=1000)
        .end()
        .agent("writer", duration_ms=5000, input_data={"articles": [1, 2]})
        .end()
        .build())


class TestClone:
    def test_deep_copy(self, trace):
        cloned = clone_trace(trace)
        assert cloned.trace_id == trace.trace_id
        assert len(cloned.spans) == len(trace.spans)
        # Modify clone shouldn't affect original
        cloned.spans[0].name = "modified"
        assert trace.spans[0].name != "modified"


class TestSlice:
    def test_by_name(self, trace):
        sliced = slice_trace(trace, span_names={"researcher"})
        agent_names = {s.name for s in sliced.spans}
        assert "researcher" in agent_names

    def test_by_type(self, trace):
        sliced = slice_trace(trace, span_types={SpanType.TOOL})
        assert all(s.span_type == SpanType.TOOL for s in sliced.spans)

    def test_with_children(self, trace):
        sliced = slice_trace(trace, span_names={"researcher"}, include_children=True)
        names = {s.name for s in sliced.spans}
        assert "web_search" in names  # child of researcher


class TestAnonymize:
    def test_removes_data(self, trace):
        anon = anonymize_trace(trace)
        researcher = next(s for s in anon.spans if s.name == "researcher")
        # Output data should be anonymized
        assert "api_key_123" not in str(researcher.output_data)
        assert "<" in str(researcher.output_data)  # type placeholders

    def test_preserves_structure(self, trace):
        anon = anonymize_trace(trace)
        assert len(anon.spans) == len(trace.spans)
        assert all(s.name for s in anon.spans)  # names preserved


class TestMerge:
    def test_basic(self):
        t1 = TraceBuilder("a").agent("a1").end().build()
        t2 = TraceBuilder("b").agent("b1").end().build()

        merged = merge_traces([t1, t2])
        assert len(merged.spans) == 2
        names = {s.name for s in merged.spans}
        assert "a1" in names
        assert "b1" in names

    def test_failure_propagation(self):
        t1 = TraceBuilder("a").agent("ok").end().build()
        t2 = TraceBuilder("b").agent("fail", status="failed", error="boom").end().build()

        merged = merge_traces([t1, t2])
        assert merged.status == SpanStatus.FAILED
