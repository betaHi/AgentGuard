"""Tests for span-level diff."""

from datetime import UTC, datetime, timedelta

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus
from agentguard.span_diff import diff_spans


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=UTC)
    return (base + timedelta(seconds=offset_s)).isoformat()


class TestSpanDiff:
    def test_identical(self):
        t = ExecutionTrace(task="same")
        t.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        result = diff_spans(t, t)
        assert result.modified_count == 0
        assert result.unchanged_count == 1

    def test_added_span(self):
        t1 = ExecutionTrace(task="v1")
        t1.add_span(Span(name="a", status=SpanStatus.COMPLETED))

        t2 = ExecutionTrace(task="v2")
        t2.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        t2.add_span(Span(name="b", status=SpanStatus.COMPLETED))

        result = diff_spans(t1, t2)
        assert result.added_count == 1

    def test_removed_span(self):
        t1 = ExecutionTrace(task="v1")
        t1.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        t1.add_span(Span(name="b", status=SpanStatus.COMPLETED))

        t2 = ExecutionTrace(task="v2")
        t2.add_span(Span(name="a", status=SpanStatus.COMPLETED))

        result = diff_spans(t1, t2)
        assert result.removed_count == 1

    def test_status_change(self):
        t1 = ExecutionTrace(task="v1")
        t1.add_span(Span(name="agent", status=SpanStatus.COMPLETED))

        t2 = ExecutionTrace(task="v2")
        t2.add_span(Span(name="agent", status=SpanStatus.FAILED, error="crash"))

        result = diff_spans(t1, t2)
        assert result.modified_count == 1
        diffs = result.matches[0].field_diffs
        assert any(d.field_name == "status" for d in diffs)

    def test_report(self):
        t1 = ExecutionTrace(task="v1")
        t1.add_span(Span(name="a", status=SpanStatus.COMPLETED))

        t2 = ExecutionTrace(task="v2")
        t2.add_span(Span(name="b", status=SpanStatus.COMPLETED))

        result = diff_spans(t1, t2)
        report = result.to_report()
        assert "Added" in report or "Removed" in report

    def test_to_dict(self):
        t = ExecutionTrace(task="dict")
        t.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        result = diff_spans(t, t)
        d = result.to_dict()
        assert "added" in d
