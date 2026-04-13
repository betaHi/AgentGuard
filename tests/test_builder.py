"""Tests for trace builder."""

import pytest

from agentguard.builder import TraceBuilder
from agentguard.core.trace import SpanStatus, SpanType


class TestTraceBuilder:
    def test_simple(self):
        trace = (TraceBuilder("test")
            .agent("researcher", duration_ms=3000)
            .end()
            .build())
        assert len(trace.spans) == 1
        assert trace.spans[0].name == "researcher"
        assert trace.spans[0].duration_ms == pytest.approx(3000, abs=10)

    def test_nested(self):
        trace = (TraceBuilder("nested")
            .agent("orchestrator", duration_ms=5000)
                .tool("web_search", duration_ms=1000)
                .tool("parser", duration_ms=500)
            .end()
            .build())
        assert len(trace.spans) == 3
        # Tools should be children of orchestrator
        orch_id = trace.spans[0].span_id
        assert trace.spans[1].parent_span_id == orch_id
        assert trace.spans[2].parent_span_id == orch_id

    def test_handoff(self):
        trace = (TraceBuilder("handoff")
            .agent("a", duration_ms=1000).end()
            .handoff("a", "b", context_size=500)
            .agent("b", duration_ms=1000).end()
            .build())
        handoffs = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
        assert len(handoffs) == 1
        assert handoffs[0].context_size_bytes == 500

    def test_failure(self):
        trace = (TraceBuilder("fail")
            .agent("bad_agent", duration_ms=1000, status="failed", error="crash")
            .end()
            .build())
        assert trace.status == SpanStatus.FAILED
        assert trace.spans[0].error == "crash"

    def test_llm_call(self):
        trace = (TraceBuilder("llm")
            .agent("assistant", duration_ms=5000)
                .llm_call("gpt-4", duration_ms=3000, token_count=1500, cost_usd=0.05)
            .end()
            .build())
        llm = [s for s in trace.spans if s.span_type == SpanType.LLM_CALL]
        assert len(llm) == 1
        assert llm[0].token_count == 1500

    def test_wait(self):
        trace = (TraceBuilder("wait")
            .agent("a", duration_ms=1000).end()
            .wait(500)
            .agent("b", duration_ms=1000).end()
            .build())
        a_end = trace.spans[0].ended_at
        b_start = trace.spans[1].started_at
        # b should start 500ms after a ends
        assert b_start > a_end

    def test_tags(self):
        trace = (TraceBuilder("tags")
            .agent("tagged", tags=["critical", "production"])
            .end()
            .build())
        assert "critical" in trace.spans[0].tags

    def test_complex_pipeline(self):
        trace = (TraceBuilder("content_pipeline")
            .agent("researcher", duration_ms=3000, output_data={"articles": [1, 2, 3]})
                .tool("web_search", duration_ms=1500)
                .tool("pdf_parser", duration_ms=1000)
            .end()
            .handoff("researcher", "analyst", context_size=2000)
            .agent("analyst", duration_ms=4000, input_data={"articles": [1, 2, 3]})
                .llm_call("claude", duration_ms=3000, token_count=5000, cost_usd=0.15)
            .end()
            .handoff("analyst", "writer", context_size=1000)
            .agent("writer", duration_ms=2000)
            .end()
            .build())

        assert len(trace.spans) == 8
        assert trace.status == SpanStatus.COMPLETED
        agents = [s for s in trace.spans if s.span_type == SpanType.AGENT]
        assert len(agents) == 3
