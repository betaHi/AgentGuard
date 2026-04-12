"""Tests for trace normalization."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.normalize import normalize_trace


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


class TestNormalize:
    def test_clean_trace_unchanged(self):
        trace = ExecutionTrace(task="clean", started_at=_ts(0), ended_at=_ts(5), status=SpanStatus.COMPLETED)
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(5)))
        result = normalize_trace(trace)
        # Only trace_id fix expected
        assert len([c for c in result.changes if "trace_id" not in c]) <= 1

    def test_fix_orphan(self):
        trace = ExecutionTrace(task="orphan", started_at=_ts(0), ended_at=_ts(5))
        trace.add_span(Span(name="orphan", parent_span_id="nonexistent"))
        result = normalize_trace(trace)
        assert any("promoted to root" in c for c in result.changes)
        assert trace.spans[0].parent_span_id is None

    def test_deduplicate(self):
        trace = ExecutionTrace(task="dup")
        s = Span(span_id="dup1", name="a")
        trace.spans = [s, Span(span_id="dup1", name="a_copy")]
        result = normalize_trace(trace)
        assert any("duplicate" in c for c in result.changes)
        assert len(trace.spans) == 1

    def test_fix_running_spans(self):
        trace = ExecutionTrace(task="running", started_at=_ts(0), ended_at=_ts(5), status=SpanStatus.COMPLETED)
        trace.add_span(Span(name="stuck", status=SpanStatus.RUNNING, started_at=_ts(0)))
        result = normalize_trace(trace)
        assert any("Running span" in c for c in result.changes)
        assert trace.spans[0].status == SpanStatus.FAILED

    def test_fix_missing_started_at(self):
        trace = ExecutionTrace(task="no_start")
        trace.started_at = ""
        trace.add_span(Span(name="a", started_at=_ts(3), ended_at=_ts(5)))
        result = normalize_trace(trace)
        assert trace.started_at == _ts(3)

    def test_fix_trace_status(self):
        trace = ExecutionTrace(task="bad_status", started_at=_ts(0), ended_at=_ts(5), status=SpanStatus.COMPLETED)
        trace.add_span(Span(name="fail", status=SpanStatus.FAILED, error="boom"))
        result = normalize_trace(trace)
        assert trace.status == SpanStatus.FAILED

    def test_to_dict(self):
        trace = ExecutionTrace(task="dict")
        result = normalize_trace(trace)
        d = result.to_dict()
        assert "changed" in d
        assert "changes" in d
