"""Tests for trace timeline."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.timeline import build_timeline, Timeline, EventType


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


def _make_trace() -> ExecutionTrace:
    trace = ExecutionTrace(trace_id="tl-test", task="timeline", started_at=_ts(0), ended_at=_ts(10), status=SpanStatus.COMPLETED)
    trace.add_span(Span(name="researcher", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                       started_at=_ts(0), ended_at=_ts(4), output_data={"articles": [1]}))
    trace.add_span(Span(name="handoff_1", span_type=SpanType.HANDOFF, status=SpanStatus.COMPLETED,
                       handoff_from="researcher", handoff_to="writer", context_size_bytes=500,
                       started_at=_ts(4), ended_at=_ts(4)))
    trace.add_span(Span(name="writer", span_type=SpanType.AGENT, status=SpanStatus.FAILED,
                       error="out of tokens", started_at=_ts(4), ended_at=_ts(8)))
    trace.add_span(Span(name="writer_retry", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                       retry_count=1, started_at=_ts(8), ended_at=_ts(10)))
    return trace


class TestBuildTimeline:
    def test_events_created(self):
        trace = _make_trace()
        tl = build_timeline(trace)
        assert len(tl.events) > 0

    def test_events_ordered(self):
        trace = _make_trace()
        tl = build_timeline(trace)
        for i in range(len(tl.events) - 1):
            assert tl.events[i].timestamp <= tl.events[i + 1].timestamp

    def test_start_and_end_events(self):
        trace = _make_trace()
        tl = build_timeline(trace)
        starts = tl.filter_by_type(EventType.SPAN_START)
        ends = tl.filter_by_type(EventType.SPAN_END)
        assert len(starts) >= 4  # 4 spans
        assert len(ends) >= 4

    def test_failure_event(self):
        trace = _make_trace()
        tl = build_timeline(trace)
        failures = tl.filter_by_type(EventType.FAILURE)
        assert len(failures) == 1
        assert failures[0].details["error"] == "out of tokens"

    def test_handoff_event(self):
        trace = _make_trace()
        tl = build_timeline(trace)
        handoffs = tl.filter_by_type(EventType.HANDOFF)
        assert len(handoffs) == 1
        assert handoffs[0].details["from"] == "researcher"

    def test_retry_event(self):
        trace = _make_trace()
        tl = build_timeline(trace)
        retries = tl.filter_by_type(EventType.RETRY)
        assert len(retries) == 1

    def test_filter_by_span(self):
        trace = _make_trace()
        tl = build_timeline(trace)
        writer_events = tl.filter_by_span("writer")
        assert len(writer_events) >= 2  # start + end + failure

    def test_to_text(self):
        trace = _make_trace()
        tl = build_timeline(trace)
        text = tl.to_text()
        assert "researcher" in text
        assert "writer" in text

    def test_to_dict(self):
        trace = _make_trace()
        tl = build_timeline(trace)
        d = tl.to_dict()
        assert "events" in d
        assert d["trace_id"] == "tl-test"

    def test_empty_trace(self):
        trace = ExecutionTrace(task="empty")
        tl = build_timeline(trace)
        assert tl.events == []
