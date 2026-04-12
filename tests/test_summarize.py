"""Tests for trace summarizer."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.summarize import summarize_trace, summarize_brief


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


class TestSummarize:
    def test_good_trace(self):
        t = ExecutionTrace(task="content pipeline", started_at=_ts(0), ended_at=_ts(5), status=SpanStatus.COMPLETED)
        t.add_span(Span(name="a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                       started_at=_ts(0), ended_at=_ts(5), token_count=1000))
        summary = summarize_trace(t)
        assert "completed successfully" in summary
        assert "content pipeline" in summary

    def test_failed_trace(self):
        t = ExecutionTrace(task="bad pipeline", started_at=_ts(0), ended_at=_ts(5), status=SpanStatus.FAILED)
        t.add_span(Span(name="bad_agent", status=SpanStatus.FAILED, error="API timeout"))
        summary = summarize_trace(t)
        assert "failed" in summary
        assert "API timeout" in summary

    def test_brief(self):
        t = ExecutionTrace(task="quick task", started_at=_ts(0), ended_at=_ts(3), status=SpanStatus.COMPLETED)
        t.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(3)))
        brief = summarize_brief(t)
        assert "✅" in brief
        assert "quick task" in brief

    def test_with_handoffs(self):
        t = ExecutionTrace(task="handoff_test", started_at=_ts(0), ended_at=_ts(10), status=SpanStatus.COMPLETED)
        t.add_span(Span(name="h", span_type=SpanType.HANDOFF, status=SpanStatus.COMPLETED,
                       context_dropped_keys=["data"]))
        t.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(10)))
        summary = summarize_trace(t)
        assert "handoff" in summary.lower()
