"""Tests for span bottleneck category classification."""

from agentguard.analysis import analyze_bottleneck, _classify_span_category
from agentguard.core.trace import Span, SpanType, SpanStatus
from agentguard.builder import TraceBuilder


def test_tool_spans_classified_as_io():
    """Tool spans are always classified as IO."""
    span = Span(name="search", span_type=SpanType.TOOL)
    cat = _classify_span_category(span, 100, 100, [])
    assert cat == "io"


def test_metadata_model_hint_is_io():
    """Span with 'model' in metadata is IO (LLM call)."""
    span = Span(name="generator", span_type=SpanType.AGENT, metadata={"model": "gpt-4"})
    cat = _classify_span_category(span, 100, 100, [])
    assert cat == "io"


def test_high_self_time_no_children_is_cpu():
    """Span with high self-time and no IO children is CPU."""
    span = Span(name="cruncher", span_type=SpanType.AGENT)
    cat = _classify_span_category(span, 80, 100, [])
    assert cat == "cpu"


def test_low_self_time_with_children_is_waiting():
    """Span mostly waiting for children is classified as waiting."""
    span = Span(name="coordinator", span_type=SpanType.AGENT)
    child = Span(name="worker", span_type=SpanType.AGENT)
    cat = _classify_span_category(span, 10, 100, [child])
    assert cat == "waiting"


def test_zero_duration_is_unknown():
    """Zero-duration span is unknown."""
    span = Span(name="instant", span_type=SpanType.AGENT)
    cat = _classify_span_category(span, 0, 0, [])
    assert cat == "unknown"


def test_io_children_make_parent_io():
    """Parent with mostly IO children is IO."""
    span = Span(name="fetcher", span_type=SpanType.AGENT)
    children = [
        Span(name="api_call", span_type=SpanType.TOOL),
        Span(name="search", span_type=SpanType.TOOL),
    ]
    cat = _classify_span_category(span, 30, 100, children)
    assert cat == "io"


def test_category_in_bottleneck_report():
    """Bottleneck report includes category for each agent."""
    trace = (TraceBuilder("cats")
        .agent("fast", duration_ms=100).end()
        .agent("slow", duration_ms=5000)
            .tool("api", duration_ms=4000)
        .end()
        .build())
    bn = analyze_bottleneck(trace)
    categories = {a["name"]: a["category"] for a in bn.agent_rankings}
    assert "slow" in categories
    assert categories["slow"] == "io"  # has tool child


def test_category_in_report_text():
    """to_report() shows category icons."""
    trace = (TraceBuilder("report")
        .agent("worker", duration_ms=1000).end()
        .build())
    bn = analyze_bottleneck(trace)
    text = bn.to_report()
    assert any(cat in text for cat in ["io", "cpu", "waiting", "unknown"])
