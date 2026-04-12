"""Tests for trace comparison."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.comparison import compare_traces


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


class TestCompareTraces:
    def test_same_traces(self):
        t = ExecutionTrace(task="same", started_at=_ts(0), ended_at=_ts(5), status=SpanStatus.COMPLETED)
        t.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(5)))
        result = compare_traces(t, t)
        assert abs(result.score_delta) < 1

    def test_improvement(self):
        bad = ExecutionTrace(task="bad", started_at=_ts(0), ended_at=_ts(10), status=SpanStatus.FAILED)
        bad.add_span(Span(name="a", status=SpanStatus.FAILED, error="fail", started_at=_ts(0), ended_at=_ts(10)))
        
        good = ExecutionTrace(task="good", started_at=_ts(0), ended_at=_ts(3), status=SpanStatus.COMPLETED)
        good.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(3)))
        
        result = compare_traces(bad, good)
        assert result.score_delta > 0
        assert "improvement" in result.summary.lower()

    def test_structural_diff(self):
        t1 = ExecutionTrace(task="v1")
        t1.add_span(Span(name="agent_a", status=SpanStatus.COMPLETED))
        
        t2 = ExecutionTrace(task="v2")
        t2.add_span(Span(name="agent_a", status=SpanStatus.COMPLETED))
        t2.add_span(Span(name="agent_b", status=SpanStatus.COMPLETED))
        
        result = compare_traces(t1, t2)
        assert "agent_b" in str(result.structural_changes)

    def test_report(self):
        t = ExecutionTrace(task="report", started_at=_ts(0), ended_at=_ts(5))
        t.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(5)))
        result = compare_traces(t, t)
        report = result.to_report()
        assert "Comparison" in report

    def test_to_dict(self):
        t = ExecutionTrace(task="dict")
        t.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        result = compare_traces(t, t)
        d = result.to_dict()
        assert "scores" in d
        assert "metric_deltas" in d
