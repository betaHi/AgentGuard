"""Edge case tests for trace scoring."""

from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.scoring import score_trace


class TestScoringEdgeCases:
    def test_single_span(self):
        trace = (TraceBuilder("single")
            .agent("solo", duration_ms=1000)
            .end()
            .build())
        score = score_trace(trace)
        assert 50 <= score.overall <= 100

    def test_only_tools(self):
        """Trace with only tool spans (no agents)."""
        trace = ExecutionTrace(task="tools_only")
        trace.add_span(Span(name="tool1", span_type=SpanType.TOOL, status=SpanStatus.COMPLETED))
        trace.add_span(Span(name="tool2", span_type=SpanType.TOOL, status=SpanStatus.COMPLETED))
        score = score_trace(trace)
        assert score.overall >= 0

    def test_all_timeout(self):
        trace = ExecutionTrace(task="timeout")
        trace.add_span(Span(name="slow", status=SpanStatus.TIMEOUT))
        score = score_trace(trace)
        assert score.grade in ("D", "F")

    def test_mixed_statuses(self):
        trace = ExecutionTrace(task="mixed")
        trace.add_span(Span(name="ok", status=SpanStatus.COMPLETED))
        trace.add_span(Span(name="fail", status=SpanStatus.FAILED, error="boom"))
        trace.add_span(Span(name="running", status=SpanStatus.RUNNING))
        trace.add_span(Span(name="timeout", status=SpanStatus.TIMEOUT))
        score = score_trace(trace)
        assert 10 <= score.overall <= 80

    def test_high_retry_penalty(self):
        """Many retries should reduce efficiency score."""
        trace = (TraceBuilder("retries")
            .agent("a")
                .tool("flaky", retry_count=10)
                .tool("flaky2", retry_count=10)
            .end()
            .build())
        score = score_trace(trace)
        eff = next(c for c in score.components if c.name == "Efficiency")
        assert eff.score < 80  # penalized for retries

    def test_expected_duration_fast(self):
        """Trace completing faster than expected should score well."""
        trace = (TraceBuilder("fast")
            .agent("speedy", duration_ms=500)
            .end()
            .build())
        score = score_trace(trace, expected_duration_ms=10000)
        perf = next(c for c in score.components if c.name == "Performance")
        assert perf.score == 100

    def test_expected_duration_slow(self):
        """Trace much slower than expected should score poorly."""
        trace = (TraceBuilder("slow")
            .agent("turtle", duration_ms=30000)
            .end()
            .build())
        score = score_trace(trace, expected_duration_ms=5000)
        perf = next(c for c in score.components if c.name == "Performance")
        assert perf.score < 50

    def test_handoff_with_full_utilization(self):
        """Perfect context utilization should score well."""
        from agentguard import mark_context_used, record_handoff
        from agentguard.sdk.recorder import finish_recording, init_recorder

        init_recorder(task="handoff_score_test")
        ctx = {"data": [1, 2], "meta": "info"}
        h = record_handoff("a", "b", context=ctx)
        mark_context_used(h, used_keys=["data", "meta"])
        trace = finish_recording()

        score = score_trace(trace)
        ctx_score = next(c for c in score.components if c.name == "Context Integrity")
        assert ctx_score.score == 100  # full utilization
