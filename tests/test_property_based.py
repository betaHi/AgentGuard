"""Property-based tests: random trace generation + serialization roundtrip.

Uses Hypothesis to generate arbitrary valid traces and verify that
serialization/deserialization preserves structure, and analysis
functions never crash on valid input.
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.export import export_otel
from agentguard.importer import import_otel


# ── Strategies ──

_span_types = st.sampled_from([SpanType.AGENT, SpanType.TOOL, SpanType.HANDOFF])
_statuses = st.sampled_from([SpanStatus.COMPLETED, SpanStatus.FAILED])
_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=15
)
_iso_ts = st.just("2025-01-01T00:00:00+00:00")


@st.composite
def span_strategy(draw):
    """Generate a random valid Span."""
    return Span(
        name=draw(_names),
        span_type=draw(_span_types),
        started_at=draw(_iso_ts),
        ended_at="2025-01-01T00:00:01+00:00",
        status=draw(_statuses),
        error=draw(st.one_of(st.none(), st.text(max_size=30))),
        metadata=draw(st.fixed_dictionaries({}, optional={
            "key": st.text(max_size=10),
        })),
    )


@st.composite
def trace_strategy(draw):
    """Generate a random valid ExecutionTrace with 1-20 spans."""
    task = draw(st.text(min_size=1, max_size=20,
                        alphabet="abcdefghijklmnopqrstuvwxyz "))
    trace = ExecutionTrace(task=task)
    trace.started_at = "2025-01-01T00:00:00+00:00"

    n_spans = draw(st.integers(min_value=1, max_value=20))
    spans = [draw(span_strategy()) for _ in range(n_spans)]

    # Optionally parent some spans to earlier ones
    for i, span in enumerate(spans):
        if i > 0 and draw(st.booleans()):
            parent_idx = draw(st.integers(min_value=0, max_value=i - 1))
            span.parent_span_id = spans[parent_idx].span_id
        trace.add_span(span)

    trace.ended_at = "2025-01-01T00:00:02+00:00"
    trace.status = SpanStatus.COMPLETED
    return trace


# ── Properties ──

class TestOtelRoundtrip:
    @given(trace=trace_strategy())
    @settings(max_examples=50, deadline=5000)
    def test_span_count_preserved(self, trace):
        """OTel export→import preserves span count."""
        otel = export_otel(trace)
        reimported = import_otel(otel)
        assert len(reimported.spans) == len(trace.spans)

    @given(trace=trace_strategy())
    @settings(max_examples=50, deadline=5000)
    def test_span_names_preserved(self, trace):
        """OTel export→import preserves all span names."""
        otel = export_otel(trace)
        reimported = import_otel(otel)
        orig_names = sorted(s.name for s in trace.spans)
        # OTel names are prefixed with "type:", extract original
        reimported_names = sorted(s.name for s in reimported.spans)
        for orig in orig_names:
            assert any(orig in rn for rn in reimported_names), (
                f"Name '{orig}' lost in roundtrip"
            )

    @given(trace=trace_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_otel_json_valid(self, trace):
        """OTel export produces valid JSON structure."""
        import json
        otel = export_otel(trace)
        serialized = json.dumps(otel)
        parsed = json.loads(serialized)
        assert "resourceSpans" in parsed


class TestAnalysisNeverCrashes:
    @given(trace=trace_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_analyze_failures(self, trace):
        from agentguard.analysis import analyze_failures
        result = analyze_failures(trace)
        assert result.total_failed_spans >= 0

    @given(trace=trace_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_analyze_bottleneck(self, trace):
        from agentguard.analysis import analyze_bottleneck
        result = analyze_bottleneck(trace)
        assert isinstance(result.bottleneck_span, str)

    @given(trace=trace_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_analyze_flow(self, trace):
        from agentguard.analysis import analyze_flow
        result = analyze_flow(trace)
        assert isinstance(result.handoffs, list)

    @given(trace=trace_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_propagation(self, trace):
        from agentguard.propagation import analyze_propagation
        result = analyze_propagation(trace)
        assert result.total_failures >= 0
