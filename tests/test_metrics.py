"""Tests for metrics extraction."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.metrics import extract_metrics, _percentile


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


class TestPercentile:
    def test_median(self):
        assert _percentile([1, 2, 3, 4, 5], 50) == 3

    def test_p90(self):
        vals = list(range(1, 101))
        assert _percentile(vals, 90) == pytest.approx(90.01, abs=1)

    def test_empty(self):
        assert _percentile([], 50) == 0


class TestExtractMetrics:
    def test_basic(self):
        trace = ExecutionTrace(task="test", started_at=_ts(0), ended_at=_ts(10))
        trace.add_span(Span(name="a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                           started_at=_ts(0), ended_at=_ts(5), token_count=100, estimated_cost_usd=0.01))
        trace.add_span(Span(name="t", span_type=SpanType.TOOL, status=SpanStatus.COMPLETED,
                           started_at=_ts(5), ended_at=_ts(8)))
        trace.add_span(Span(name="h", span_type=SpanType.HANDOFF, status=SpanStatus.COMPLETED,
                           context_size_bytes=500))
        
        m = extract_metrics(trace)
        assert m.agent_count == 1
        assert m.tool_count == 1
        assert m.handoff_count == 1
        assert m.total_tokens == 100
        assert m.total_cost_usd == pytest.approx(0.01)
        assert m.total_context_bytes == 500

    def test_duration_percentiles(self):
        trace = ExecutionTrace(task="dur")
        for i in range(10):
            trace.add_span(Span(name=f"a{i}", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                              started_at=_ts(i * 2), ended_at=_ts(i * 2 + (i + 1))))
        m = extract_metrics(trace)
        assert m.agent_duration.p50_ms > 0
        assert m.agent_duration.p90_ms >= m.agent_duration.p50_ms

    def test_error_rate(self):
        trace = ExecutionTrace(task="err")
        trace.add_span(Span(name="ok", status=SpanStatus.COMPLETED))
        trace.add_span(Span(name="fail", status=SpanStatus.FAILED, error="boom"))
        
        m = extract_metrics(trace)
        assert m.success_rate == 0.5
        assert m.error_rate == 0.5

    def test_retry_rate(self):
        trace = ExecutionTrace(task="retry")
        trace.add_span(Span(name="no_retry", status=SpanStatus.COMPLETED))
        trace.add_span(Span(name="retried", status=SpanStatus.COMPLETED, retry_count=3))
        
        m = extract_metrics(trace)
        assert m.retry_rate == 0.5

    def test_to_dict(self):
        trace = ExecutionTrace(task="dict")
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(1)))
        m = extract_metrics(trace)
        d = m.to_dict()
        assert "overall_duration" in d
        assert "p50_ms" in d["overall_duration"]

    def test_prometheus_output(self):
        trace = ExecutionTrace(trace_id="prom-test", task="prom")
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(1)))
        m = extract_metrics(trace)
        prom = m.to_prometheus()
        assert "agentguard_span_count" in prom
        assert "prom-test" in prom

    def test_empty_trace(self):
        trace = ExecutionTrace(task="empty")
        m = extract_metrics(trace)
        assert m.span_count == 0
        assert m.success_rate == 0
