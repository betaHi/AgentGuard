"""Tests for trace aggregation."""

from datetime import UTC, datetime, timedelta

from agentguard.aggregate import aggregate_traces
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=UTC)
    return (base + timedelta(seconds=offset_s)).isoformat()


def _good_trace(idx: int = 0) -> ExecutionTrace:
    trace = ExecutionTrace(task=f"good_{idx}", started_at=_ts(idx * 10),
                          ended_at=_ts(idx * 10 + 5), status=SpanStatus.COMPLETED)
    trace.add_span(Span(name="agent_a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                       started_at=_ts(idx * 10), ended_at=_ts(idx * 10 + 3)))
    trace.add_span(Span(name="agent_b", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                       started_at=_ts(idx * 10 + 3), ended_at=_ts(idx * 10 + 5)))
    return trace


def _bad_trace(idx: int = 0) -> ExecutionTrace:
    trace = ExecutionTrace(task=f"bad_{idx}", started_at=_ts(idx * 10),
                          ended_at=_ts(idx * 10 + 8), status=SpanStatus.FAILED)
    trace.add_span(Span(name="agent_a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                       started_at=_ts(idx * 10), ended_at=_ts(idx * 10 + 3)))
    trace.add_span(Span(name="agent_b", span_type=SpanType.AGENT, status=SpanStatus.FAILED,
                       error="API timeout", started_at=_ts(idx * 10 + 3), ended_at=_ts(idx * 10 + 8)))
    return trace


class TestAggregateTraces:
    def test_empty(self):
        result = aggregate_traces([])
        assert result.trace_count == 0
        assert result.success_rate == 0

    def test_all_good(self):
        traces = [_good_trace(i) for i in range(5)]
        result = aggregate_traces(traces)
        assert result.trace_count == 5
        assert result.success_rate == 1.0
        assert result.avg_score > 70

    def test_mixed(self):
        traces = [_good_trace(0), _good_trace(1), _bad_trace(2)]
        result = aggregate_traces(traces)
        assert result.trace_count == 3
        assert result.success_count == 2
        assert result.failure_count == 1

    def test_agent_stats(self):
        traces = [_good_trace(0), _bad_trace(1)]
        result = aggregate_traces(traces)

        agent_a = next((a for a in result.agent_stats if a.name == "agent_a"), None)
        assert agent_a is not None
        assert agent_a.total_invocations == 2
        assert agent_a.success_rate == 1.0

    def test_common_errors(self):
        traces = [_bad_trace(i) for i in range(3)]
        result = aggregate_traces(traces)
        assert len(result.common_errors) >= 1
        assert result.common_errors[0]["count"] == 3

    def test_score_trend(self):
        traces = [_good_trace(i) for i in range(5)]
        result = aggregate_traces(traces)
        assert len(result.score_trend) == 5

    def test_report(self):
        traces = [_good_trace(0), _bad_trace(1)]
        result = aggregate_traces(traces)
        report = result.to_report()
        assert "Aggregate" in report
        assert "agent_a" in report or "agent_b" in report

    def test_to_dict(self):
        traces = [_good_trace(0)]
        result = aggregate_traces(traces)
        d = result.to_dict()
        assert "trace_count" in d
        assert "agent_stats" in d
