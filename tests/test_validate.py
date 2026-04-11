"""Tests for trace validation."""

from agentguard.core.trace import ExecutionTrace, Span, SpanType
from agentguard.validate import validate_trace


def test_valid_trace():
    t = ExecutionTrace(task="test")
    s = Span(name="agent", span_type=SpanType.AGENT)
    s.complete()
    t.add_span(s)
    t.complete()
    r = validate_trace(t)
    assert r.valid
    assert len(r.errors) == 0


def test_orphan_span():
    t = ExecutionTrace(task="test")
    s = Span(name="orphan", span_type=SpanType.AGENT, parent_span_id="nonexistent")
    t.add_span(s)
    r = validate_trace(t)
    assert not r.valid
    assert any("Orphan" in i.message for i in r.issues)


def test_empty_trace():
    t = ExecutionTrace(task="empty")
    r = validate_trace(t)
    assert r.valid  # empty is valid but warns
    assert len(r.warnings) >= 1


def test_duplicate_ids():
    t = ExecutionTrace(task="test")
    s1 = Span(name="a", span_type=SpanType.AGENT)
    s2 = Span(name="b", span_type=SpanType.AGENT)
    s2.span_id = s1.span_id  # force duplicate
    t.add_span(s1)
    t.add_span(s2)
    r = validate_trace(t)
    assert not r.valid
    assert any("Duplicate" in i.message for i in r.issues)
