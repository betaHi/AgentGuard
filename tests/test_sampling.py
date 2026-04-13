"""Tests for SDK trace sampling — record only N% of traces (per-trace).

Sampling decision is made ONCE per TraceRecorder instance, not per-span.
This ensures all spans in a trace are either all recorded or all skipped.
"""

import agentguard
from agentguard.sdk.recorder import TraceRecorder, init_recorder, get_recorder
from agentguard.sdk.decorators import record_agent
from agentguard.settings import reset_settings
from agentguard.core.trace import Span, SpanType
import pytest


class TestTraceLevelSampling:
    def setup_method(self):
        reset_settings()

    def teardown_method(self):
        reset_settings()

    def test_default_rate_records_all(self):
        """Default sampling_rate=1.0 always records."""
        rec = TraceRecorder(task="test")
        assert rec._sampled is True

    def test_zero_rate_skips_all(self):
        agentguard.configure(sampling_rate=0.0)
        rec = TraceRecorder(task="test")
        assert rec._sampled is False

    def test_full_rate_records_all(self):
        agentguard.configure(sampling_rate=1.0)
        rec = TraceRecorder(task="test")
        assert rec._sampled is True

    def test_decision_is_per_trace_not_per_span(self):
        """All spans in one recorder share the same sampling decision."""
        agentguard.configure(sampling_rate=1.0)
        rec = TraceRecorder(task="test")
        s1 = Span(span_type=SpanType.AGENT, name="a")
        s2 = Span(span_type=SpanType.AGENT, name="b")
        rec.push_span(s1)
        rec.push_span(s2)
        # Both should be recorded
        assert len(rec.trace.spans) == 2

    def test_sampled_out_records_zero_spans(self):
        """When sampled out, no spans are recorded."""
        agentguard.configure(sampling_rate=0.0)
        rec = TraceRecorder(task="test")
        s = Span(span_type=SpanType.AGENT, name="a")
        rec.push_span(s)
        assert len(rec.trace.spans) == 0

    def test_sampled_out_pop_is_noop(self):
        agentguard.configure(sampling_rate=0.0)
        rec = TraceRecorder(task="test")
        s = Span(span_type=SpanType.AGENT, name="a")
        rec.push_span(s)
        rec.pop_span(s)  # should not raise

    def test_partial_rate_probabilistic(self):
        """50% rate produces roughly half sampled."""
        agentguard.configure(sampling_rate=0.5)
        sampled = sum(TraceRecorder(task="t")._sampled for _ in range(200))
        assert 50 < sampled < 150, f"Got {sampled}/200"

    def test_decorated_fn_works_when_sampled_out(self):
        agentguard.configure(sampling_rate=0.0)

        @record_agent(name="test")
        def my_fn(x):
            return x * 3

        assert my_fn(7) == 21

    def test_exception_raised_when_sampled_out(self):
        agentguard.configure(sampling_rate=0.0)

        @record_agent(name="test")
        def failing():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            failing()

    def test_no_partial_traces(self):
        """Verify no partial traces: all or nothing."""
        agentguard.configure(sampling_rate=0.0)
        rec = TraceRecorder(task="test")
        for i in range(5):
            s = Span(span_type=SpanType.AGENT, name=f"agent_{i}")
            rec.push_span(s)
        # All 5 should be skipped
        assert len(rec.trace.spans) == 0
