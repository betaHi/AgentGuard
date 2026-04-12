"""Tests for trace scoring."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.scoring import score_trace, TraceScore


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


class TestScoreTrace:
    def test_perfect_trace(self):
        """All-green trace should score high."""
        trace = ExecutionTrace(task="good", started_at=_ts(0), ended_at=_ts(5), status=SpanStatus.COMPLETED)
        trace.add_span(Span(name="a1", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                           started_at=_ts(0), ended_at=_ts(3)))
        trace.add_span(Span(name="a2", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                           started_at=_ts(3), ended_at=_ts(5)))
        
        score = score_trace(trace)
        assert score.overall >= 70
        assert score.grade in ("A", "B", "C")

    def test_all_failed_trace(self):
        """All-failed trace should score low."""
        trace = ExecutionTrace(task="bad", started_at=_ts(0), ended_at=_ts(5), status=SpanStatus.FAILED)
        trace.add_span(Span(name="a1", status=SpanStatus.FAILED, error="boom",
                           started_at=_ts(0), ended_at=_ts(2)))
        trace.add_span(Span(name="a2", status=SpanStatus.FAILED, error="crash",
                           started_at=_ts(2), ended_at=_ts(5)))
        
        score = score_trace(trace)
        assert score.overall < 50
        assert score.grade in ("D", "F")

    def test_with_expected_duration(self):
        """Performance should degrade when exceeding expected duration."""
        trace = ExecutionTrace(task="slow", started_at=_ts(0), ended_at=_ts(10), status=SpanStatus.COMPLETED)
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(10)))
        
        # Within expected duration
        fast_score = score_trace(trace, expected_duration_ms=20000)
        # Way over expected duration
        slow_score = score_trace(trace, expected_duration_ms=2000)
        
        assert fast_score.overall > slow_score.overall

    def test_empty_trace(self):
        """Empty trace should handle gracefully."""
        trace = ExecutionTrace(task="empty")
        score = score_trace(trace)
        assert isinstance(score, TraceScore)
        assert score.overall >= 0

    def test_resilient_trace(self):
        """Trace with handled failures should score higher on resilience."""
        trace = ExecutionTrace(task="resilient", started_at=_ts(0), ended_at=_ts(5), status=SpanStatus.COMPLETED)
        trace.add_span(Span(span_id="parent", name="orch", span_type=SpanType.AGENT,
                           status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(5)))
        trace.add_span(Span(name="tool", span_type=SpanType.TOOL, parent_span_id="parent",
                           status=SpanStatus.FAILED, error="retry worked", failure_handled=True,
                           started_at=_ts(0), ended_at=_ts(1)))
        
        score = score_trace(trace)
        resilience = next(c for c in score.components if c.name == "Resilience")
        assert resilience.score >= 50

    def test_report_output(self):
        """Report should be a readable string."""
        trace = ExecutionTrace(task="report", started_at=_ts(0), ended_at=_ts(5))
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(5)))
        
        score = score_trace(trace)
        report = score.to_report()
        assert "Score" in report
        assert score.grade in report

    def test_to_dict(self):
        """Serialization should work."""
        trace = ExecutionTrace(task="dict")
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        
        score = score_trace(trace)
        d = score.to_dict()
        assert "overall" in d
        assert "grade" in d
        assert "components" in d

    def test_grade_boundaries(self):
        """Grades should follow expected boundaries."""
        from agentguard.scoring import _grade
        assert _grade(95) == "A"
        assert _grade(85) == "B"
        assert _grade(75) == "C"
        assert _grade(65) == "D"
        assert _grade(50) == "F"
