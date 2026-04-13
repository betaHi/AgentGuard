"""Tests for SDK span annotations — user-attached key-value metadata."""

from agentguard.sdk.recorder import TraceRecorder, annotate, get_recorder
from agentguard.sdk.decorators import record_agent
from agentguard.core.trace import Span, SpanType


class TestAnnotateSpan:
    def test_annotate_current_span(self):
        rec = TraceRecorder(task="test")
        s = Span(span_type=SpanType.AGENT, name="a")
        rec.push_span(s)
        rec.annotate_span("model", "gpt-4")
        rec.annotate_span("temp", 0.7)
        assert s.metadata["model"] == "gpt-4"
        assert s.metadata["temp"] == 0.7

    def test_annotate_no_span_is_noop(self):
        rec = TraceRecorder(task="test")
        rec.annotate_span("key", "val")  # no crash

    def test_annotate_overwrites(self):
        rec = TraceRecorder(task="test")
        s = Span(span_type=SpanType.AGENT, name="a")
        rec.push_span(s)
        rec.annotate_span("k", "v1")
        rec.annotate_span("k", "v2")
        assert s.metadata["k"] == "v2"

    def test_annotate_multiple_keys(self):
        rec = TraceRecorder(task="test")
        s = Span(span_type=SpanType.AGENT, name="a")
        rec.push_span(s)
        for i in range(10):
            rec.annotate_span(f"key_{i}", i)
        assert len(s.metadata) >= 10

    def test_module_level_annotate_failopen(self):
        """Module-level annotate() doesn't crash even without active span."""
        annotate("key", "value")  # should not raise

    def test_annotation_survives_serialization(self):
        import json
        rec = TraceRecorder(task="test")
        s = Span(span_type=SpanType.AGENT, name="a")
        rec.push_span(s)
        rec.annotate_span("custom", {"nested": True})
        d = s.to_dict()
        assert d["metadata"]["custom"] == {"nested": True}
        json.dumps(d)  # serializable

    def test_annotate_in_decorated_fn(self):
        """Can annotate inside a decorated function."""
        @record_agent(name="my-agent")
        def my_fn():
            annotate("step", "processing")
            return 42

        result = my_fn()
        assert result == 42

    def test_package_level_import(self):
        import agentguard
        assert hasattr(agentguard, 'annotate')
