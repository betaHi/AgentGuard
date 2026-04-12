"""Tests for A/B testing."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.ab_test import ab_test, ABResult


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


def _good_trace() -> ExecutionTrace:
    t = ExecutionTrace(task="good", started_at=_ts(0), ended_at=_ts(3), status=SpanStatus.COMPLETED)
    t.add_span(Span(name="a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                   started_at=_ts(0), ended_at=_ts(3)))
    return t


def _bad_trace() -> ExecutionTrace:
    t = ExecutionTrace(task="bad", started_at=_ts(0), ended_at=_ts(10), status=SpanStatus.FAILED)
    t.add_span(Span(name="a", span_type=SpanType.AGENT, status=SpanStatus.FAILED, error="fail",
                   started_at=_ts(0), ended_at=_ts(10)))
    return t


class TestABTest:
    def test_b_wins(self):
        group_a = [_bad_trace() for _ in range(3)]
        group_b = [_good_trace() for _ in range(3)]
        result = ab_test(group_a, group_b)
        assert result.winner == "b"
        assert result.score_delta > 0

    def test_a_wins(self):
        group_a = [_good_trace() for _ in range(3)]
        group_b = [_bad_trace() for _ in range(3)]
        result = ab_test(group_a, group_b)
        assert result.winner == "a"
        assert result.score_delta < 0

    def test_tie(self):
        group_a = [_good_trace() for _ in range(3)]
        group_b = [_good_trace() for _ in range(3)]
        result = ab_test(group_a, group_b, significance_threshold=5.0)
        assert result.winner == "tie"

    def test_report(self):
        group_a = [_good_trace()]
        group_b = [_bad_trace()]
        result = ab_test(group_a, group_b, name_a="v1", name_b="v2")
        report = result.to_report()
        assert "v1" in report
        assert "v2" in report

    def test_to_dict(self):
        result = ab_test([_good_trace()], [_good_trace()])
        d = result.to_dict()
        assert "winner" in d
        assert "score_delta" in d

    def test_regressions_detected(self):
        group_a = [_good_trace() for _ in range(3)]
        group_b = [_bad_trace() for _ in range(3)]
        result = ab_test(group_a, group_b)
        assert len(result.regressions) >= 1

    def test_improvements_detected(self):
        group_a = [_bad_trace() for _ in range(3)]
        group_b = [_good_trace() for _ in range(3)]
        result = ab_test(group_a, group_b)
        assert len(result.improvements) >= 1
