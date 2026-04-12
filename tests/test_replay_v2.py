"""Tests for trace replay v2."""

import pytest
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.builder import TraceBuilder
from agentguard.replay_v2 import TraceReplay, mutate_trace


@pytest.fixture
def sample_trace():
    return (TraceBuilder("replay_test")
        .agent("researcher", duration_ms=3000, output_data={"articles": [1, 2]})
            .tool("web_search", duration_ms=1000)
        .end()
        .agent("writer", duration_ms=5000, output_data={"draft": "text"})
        .end()
        .build())


class TestTraceReplay:
    def test_assert_completed(self, sample_trace):
        replay = TraceReplay().assert_completed("researcher")
        result = replay.replay(sample_trace)
        assert result.all_passed

    def test_assert_failed_span(self):
        trace = (TraceBuilder("fail")
            .agent("bad", duration_ms=1000, status="failed", error="crash")
            .end()
            .build())
        
        replay = TraceReplay().assert_completed("bad")
        result = replay.replay(trace)
        assert not result.all_passed
        assert result.failed == 1

    def test_assert_duration(self, sample_trace):
        replay = TraceReplay().assert_duration_below("researcher", 10000)
        result = replay.replay(sample_trace)
        assert result.all_passed

    def test_assert_has_output(self, sample_trace):
        replay = TraceReplay().assert_has_output("researcher")
        result = replay.replay(sample_trace)
        assert result.all_passed

    def test_assert_no_errors(self, sample_trace):
        replay = TraceReplay().assert_no_errors()
        result = replay.replay(sample_trace)
        assert result.all_passed

    def test_missing_span(self, sample_trace):
        replay = TraceReplay().assert_completed("nonexistent")
        result = replay.replay(sample_trace)
        assert not result.all_passed

    def test_report(self, sample_trace):
        replay = TraceReplay().assert_completed("researcher")
        result = replay.replay(sample_trace)
        report = result.to_report()
        assert "PASSED" in report

    def test_chaining(self, sample_trace):
        replay = (TraceReplay()
            .assert_completed("researcher")
            .assert_completed("writer")
            .assert_has_output("researcher")
            .assert_duration_below("writer", 20000))
        result = replay.replay(sample_trace)
        assert result.all_passed
        assert result.total_assertions == 4


class TestMutateTrace:
    def test_random_failure(self, sample_trace):
        mutated = mutate_trace(sample_trace, "random_failure")
        failed = [s for s in mutated.spans if s.status == SpanStatus.FAILED]
        assert len(failed) >= 1

    def test_slow_down(self, sample_trace):
        mutated = mutate_trace(sample_trace, "slow_down")
        # Durations should be roughly doubled
        for orig, mut in zip(sample_trace.spans, mutated.spans):
            if orig.duration_ms and mut.duration_ms:
                assert mut.duration_ms >= orig.duration_ms

    def test_drop_context(self, sample_trace):
        mutated = mutate_trace(sample_trace, "drop_context")
        agents = [s for s in mutated.spans if s.span_type == SpanType.AGENT]
        assert all(s.output_data is None for s in agents)
