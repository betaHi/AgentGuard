"""Tests for trace replay v2."""

import pytest

from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace, SpanStatus, SpanType
from agentguard.replay import TraceReplay, mutate_trace


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
        for orig, mut in zip(sample_trace.spans, mutated.spans, strict=False):
            if orig.duration_ms and mut.duration_ms:
                assert mut.duration_ms >= orig.duration_ms

    def test_drop_context(self, sample_trace):
        mutated = mutate_trace(sample_trace, "drop_context")
        agents = [s for s in mutated.spans if s.span_type == SpanType.AGENT]
        assert all(s.output_data is None for s in agents)


import json
import tempfile
from pathlib import Path

from agentguard.replay import compare_golden, replay_golden


class TestGoldenReplay:
    def test_identical_traces_pass(self, sample_trace):
        """Identical golden and current should pass all assertions."""
        result = compare_golden(sample_trace, sample_trace)
        assert result.all_passed

    def test_missing_agent_fails(self, sample_trace):
        """Current trace missing a golden agent should fail."""
        # Golden has researcher + writer; current only has researcher
        current = (TraceBuilder("partial")
            .agent("researcher", duration_ms=3000, output_data={"articles": [1]})
            .end()
            .build())
        result = compare_golden(sample_trace, current)
        assert not result.all_passed
        missing = [r for r in result.results if "missing" in r.message]
        assert len(missing) >= 1

    def test_status_regression_fails(self, sample_trace):
        """Agent that was completed but is now failed should fail."""
        current = (TraceBuilder("regressed")
            .agent("researcher", duration_ms=3000, status="failed", error="crash")
                .tool("web_search", duration_ms=1000)
            .end()
            .agent("writer", duration_ms=5000, output_data={"draft": "text"})
            .end()
            .build())
        result = compare_golden(sample_trace, current)
        assert not result.all_passed
        regression = [r for r in result.results if "regressed" in r.message]
        assert len(regression) >= 1

    def test_duration_tolerance(self):
        """Duration exceeding tolerance should fail."""
        golden = (TraceBuilder("fast")
            .agent("a", duration_ms=100).end().build())
        slow = (TraceBuilder("slow")
            .agent("a", duration_ms=1000).end().build())

        # With tight tolerance
        result = compare_golden(golden, slow, tolerance_ms=100)
        duration_checks = [r for r in result.results if "duration" in r.assertion_name]
        assert any(not r.passed for r in duration_checks)

        # With loose tolerance
        result2 = compare_golden(golden, slow, tolerance_ms=2000)
        duration_checks2 = [r for r in result2.results if "duration" in r.assertion_name]
        assert all(r.passed for r in duration_checks2)

    def test_score_regression(self):
        """Score drop beyond threshold should fail."""
        golden = (TraceBuilder("good")
            .agent("a", duration_ms=100, output_data={"x": 1}).end().build())
        bad = (TraceBuilder("bad")
            .agent("a", duration_ms=100, status="failed", error="err").end().build())

        result = compare_golden(golden, bad, score_threshold=-5)
        score_checks = [r for r in result.results if "score" in r.assertion_name]
        assert any(not r.passed for r in score_checks)

    def test_replay_golden_from_file(self, sample_trace):
        """replay_golden loads from disk and compares."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_path = Path(tmpdir) / "golden.json"
            golden_path.write_text(sample_trace.to_json(), encoding="utf-8")

            result = replay_golden(str(golden_path), sample_trace)
            assert result.all_passed

    def test_replay_golden_file_not_found(self, sample_trace):
        """replay_golden raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            replay_golden("/nonexistent/path.json", sample_trace)

    def test_replay_golden_invalid_json(self, sample_trace):
        """replay_golden raises ValueError for bad JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = Path(tmpdir) / "bad.json"
            bad_path.write_text("{invalid", encoding="utf-8")
            with pytest.raises(ValueError, match="Invalid JSON"):
                replay_golden(str(bad_path), sample_trace)

    def test_replay_golden_invalid_trace(self, sample_trace):
        """replay_golden raises ValueError for valid JSON but bad trace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = Path(tmpdir) / "bad.json"
            bad_path.write_text('{"not": "a trace"}', encoding="utf-8")
            with pytest.raises(ValueError, match="Invalid trace"):
                replay_golden(str(bad_path), sample_trace)

    def test_to_dict_serializable(self, sample_trace):
        """compare_golden result is JSON-serializable."""
        result = compare_golden(sample_trace, sample_trace)
        serialized = json.dumps(result.to_dict())
        assert "all_passed" in serialized

    def test_empty_golden(self):
        """Empty golden trace (no agents) passes vacuously."""
        golden = ExecutionTrace(task="empty")
        golden.complete()
        current = (TraceBuilder("has agents")
            .agent("a", duration_ms=100).end().build())
        result = compare_golden(golden, current)
        # Only score assertion, should pass
        assert result.total_assertions >= 1
