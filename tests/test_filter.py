"""Tests for trace filtering and sampling."""

from datetime import UTC, datetime, timedelta

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.filter import (
    and_filter,
    by_duration,
    by_metadata,
    by_name,
    by_status,
    by_tag,
    by_type,
    filter_spans,
    filter_traces,
    has_error,
    has_retries,
    is_handoff,
    is_slow,
    not_filter,
    or_filter,
    sample_traces,
    trace_has_agent,
    trace_has_failures,
)


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=UTC)
    return (base + timedelta(seconds=offset_s)).isoformat()


def _make_trace() -> ExecutionTrace:
    trace = ExecutionTrace(task="filter_test", started_at=_ts(0), ended_at=_ts(10), status=SpanStatus.COMPLETED)
    trace.add_span(Span(name="researcher", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                       tags=["critical"], started_at=_ts(0), ended_at=_ts(3)))
    trace.add_span(Span(name="web_search", span_type=SpanType.TOOL, status=SpanStatus.COMPLETED,
                       started_at=_ts(0), ended_at=_ts(1)))
    trace.add_span(Span(name="writer", span_type=SpanType.AGENT, status=SpanStatus.FAILED,
                       error="out of tokens", started_at=_ts(3), ended_at=_ts(8)))
    trace.add_span(Span(name="retry_tool", span_type=SpanType.TOOL, status=SpanStatus.COMPLETED,
                       retry_count=3, metadata={"model": "gpt-4"},
                       started_at=_ts(8), ended_at=_ts(10)))
    trace.add_span(Span(name="handoff_1", span_type=SpanType.HANDOFF, status=SpanStatus.COMPLETED,
                       handoff_from="researcher", handoff_to="writer"))
    return trace


class TestSpanFilters:
    def test_by_type(self):
        trace = _make_trace()
        agents = filter_spans(trace, by_type(SpanType.AGENT))
        assert len(agents) == 2

    def test_by_status(self):
        trace = _make_trace()
        failed = filter_spans(trace, by_status(SpanStatus.FAILED))
        assert len(failed) == 1
        assert failed[0].name == "writer"

    def test_by_name_exact(self):
        trace = _make_trace()
        result = filter_spans(trace, by_name("researcher"))
        assert len(result) == 1

    def test_by_name_regex(self):
        trace = _make_trace()
        result = filter_spans(trace, by_name(r"^web_search$"))
        assert len(result) == 1
        assert result[0].name == "web_search"

    def test_by_duration(self):
        trace = _make_trace()
        slow = filter_spans(trace, by_duration(min_ms=3000))
        assert all(s.duration_ms >= 3000 for s in slow)

    def test_by_tag(self):
        trace = _make_trace()
        result = filter_spans(trace, by_tag("critical"))
        assert len(result) == 1
        assert result[0].name == "researcher"

    def test_by_metadata(self):
        trace = _make_trace()
        result = filter_spans(trace, by_metadata("model", "gpt-4"))
        assert len(result) == 1
        assert result[0].name == "retry_tool"

    def test_has_error(self):
        trace = _make_trace()
        result = filter_spans(trace, has_error())
        assert len(result) == 1

    def test_has_retries(self):
        trace = _make_trace()
        result = filter_spans(trace, has_retries())
        assert len(result) == 1
        assert result[0].retry_count == 3

    def test_is_handoff(self):
        trace = _make_trace()
        result = filter_spans(trace, is_handoff())
        assert len(result) == 1

    def test_is_slow(self):
        trace = _make_trace()
        result = filter_spans(trace, is_slow(4000))
        assert all((s.duration_ms or 0) > 4000 for s in result)


class TestComposition:
    def test_and(self):
        trace = _make_trace()
        result = filter_spans(trace, and_filter(by_type(SpanType.AGENT), by_status(SpanStatus.FAILED)))
        assert len(result) == 1
        assert result[0].name == "writer"

    def test_or(self):
        trace = _make_trace()
        result = filter_spans(trace, or_filter(by_type(SpanType.HANDOFF), has_error()))
        assert len(result) == 2  # handoff + writer

    def test_not(self):
        trace = _make_trace()
        result = filter_spans(trace, not_filter(by_type(SpanType.AGENT)))
        assert all(s.span_type != SpanType.AGENT for s in result)


class TestTraceFilters:
    def test_trace_has_failures(self):
        good = ExecutionTrace(task="good")
        good.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        bad = ExecutionTrace(task="bad")
        bad.add_span(Span(name="a", status=SpanStatus.FAILED))

        result = filter_traces([good, bad], trace_has_failures())
        assert len(result) == 1
        assert result[0].task == "bad"

    def test_trace_has_agent(self):
        t1 = ExecutionTrace(task="t1")
        t1.add_span(Span(name="researcher", span_type=SpanType.AGENT))
        t2 = ExecutionTrace(task="t2")
        t2.add_span(Span(name="writer", span_type=SpanType.AGENT))

        result = filter_traces([t1, t2], trace_has_agent("researcher"))
        assert len(result) == 1


class TestSampling:
    def test_sample_head(self):
        traces = [ExecutionTrace(task=f"t{i}") for i in range(10)]
        result = sample_traces(traces, 3, method="head")
        assert len(result) == 3
        assert result[0].task == "t0"

    def test_sample_tail(self):
        traces = [ExecutionTrace(task=f"t{i}") for i in range(10)]
        result = sample_traces(traces, 3, method="tail")
        assert len(result) == 3
        assert result[-1].task == "t9"

    def test_sample_random(self):
        traces = [ExecutionTrace(task=f"t{i}") for i in range(10)]
        result = sample_traces(traces, 3, method="random")
        assert len(result) == 3

    def test_sample_more_than_available(self):
        traces = [ExecutionTrace(task=f"t{i}") for i in range(3)]
        result = sample_traces(traces, 10)
        assert len(result) == 3
