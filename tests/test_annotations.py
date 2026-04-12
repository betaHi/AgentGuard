"""Tests for span annotations."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.annotations import (
    Annotation, AnnotationSeverity, AnnotationCategory,
    AnnotationStore, auto_annotate,
)


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


class TestAnnotation:
    def test_create(self):
        ann = Annotation(message="test", severity=AnnotationSeverity.WARNING)
        assert ann.message == "test"
        assert ann.severity == AnnotationSeverity.WARNING

    def test_to_dict(self):
        ann = Annotation(message="test", link="https://example.com")
        d = ann.to_dict()
        assert d["message"] == "test"
        assert d["link"] == "https://example.com"

    def test_roundtrip(self):
        ann = Annotation(message="test", severity=AnnotationSeverity.CRITICAL,
                        category=AnnotationCategory.SECURITY, data={"key": "val"})
        d = ann.to_dict()
        restored = Annotation.from_dict(d)
        assert restored.message == "test"
        assert restored.severity == AnnotationSeverity.CRITICAL
        assert restored.data == {"key": "val"}


class TestAnnotationStore:
    def test_annotate_and_get(self):
        store = AnnotationStore()
        ann = Annotation(message="found issue")
        store.annotate("span1", ann)
        
        assert len(store.get("span1")) == 1
        assert store.get("span1")[0].message == "found issue"

    def test_annotate_span(self):
        store = AnnotationStore()
        span = Span(span_id="s1", name="agent")
        store.annotate_span(span, "slow!", severity=AnnotationSeverity.WARNING)
        
        assert len(store.get("s1")) == 1

    def test_get_by_severity(self):
        store = AnnotationStore()
        store.annotate("s1", Annotation(message="info", severity=AnnotationSeverity.INFO))
        store.annotate("s2", Annotation(message="warn", severity=AnnotationSeverity.WARNING))
        store.annotate("s3", Annotation(message="error", severity=AnnotationSeverity.ERROR))
        
        warnings = store.get_by_severity(AnnotationSeverity.WARNING)
        assert len(warnings) == 1
        assert warnings[0][1].message == "warn"

    def test_get_by_category(self):
        store = AnnotationStore()
        store.annotate("s1", Annotation(message="slow", category=AnnotationCategory.PERFORMANCE))
        store.annotate("s2", Annotation(message="wrong", category=AnnotationCategory.CORRECTNESS))
        
        perf = store.get_by_category(AnnotationCategory.PERFORMANCE)
        assert len(perf) == 1

    def test_count(self):
        store = AnnotationStore()
        store.annotate("s1", Annotation(message="a"))
        store.annotate("s1", Annotation(message="b"))
        store.annotate("s2", Annotation(message="c"))
        assert store.count == 3

    def test_summary(self):
        store = AnnotationStore()
        store.annotate("s1", Annotation(message="a", severity=AnnotationSeverity.INFO))
        store.annotate("s2", Annotation(message="b", severity=AnnotationSeverity.WARNING))
        
        summary = store.summary()
        assert summary["total"] == 2
        assert summary["by_severity"]["info"] == 1
        assert summary["spans_annotated"] == 2

    def test_serialization(self):
        store = AnnotationStore()
        store.annotate("s1", Annotation(message="test", severity=AnnotationSeverity.ERROR))
        
        d = store.to_dict()
        restored = AnnotationStore.from_dict(d)
        assert restored.count == 1
        assert restored.get("s1")[0].severity == AnnotationSeverity.ERROR


class TestAutoAnnotate:
    def test_flags_slow_spans(self):
        trace = ExecutionTrace(task="auto", started_at=_ts(0), ended_at=_ts(15))
        trace.add_span(Span(name="fast1", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(1)))
        trace.add_span(Span(name="fast2", status=SpanStatus.COMPLETED, started_at=_ts(1), ended_at=_ts(2)))
        trace.add_span(Span(name="slow", status=SpanStatus.COMPLETED, started_at=_ts(2), ended_at=_ts(15)))
        
        store = auto_annotate(trace)
        # "slow" span is 13s vs avg ~5s = flagged
        assert store.count >= 1
        perf = store.get_by_category(AnnotationCategory.PERFORMANCE)
        assert len(perf) >= 1

    def test_flags_failures(self):
        trace = ExecutionTrace(task="fail")
        trace.add_span(Span(name="bad", status=SpanStatus.FAILED, error="crash"))
        
        store = auto_annotate(trace)
        errors = store.get_by_severity(AnnotationSeverity.ERROR)
        assert len(errors) == 1

    def test_flags_context_loss(self):
        trace = ExecutionTrace(task="ctx")
        span = Span(name="handoff", span_type=SpanType.HANDOFF, context_dropped_keys=["data"])
        trace.add_span(span)
        
        store = auto_annotate(trace)
        ctx = store.get_by_category(AnnotationCategory.CONTEXT)
        assert len(ctx) == 1

    def test_empty_trace(self):
        trace = ExecutionTrace(task="empty")
        store = auto_annotate(trace)
        assert store.count == 0
