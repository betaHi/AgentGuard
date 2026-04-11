"""Tests for export utilities."""

import json
import tempfile
from pathlib import Path
from agentguard.core.trace import ExecutionTrace, Span, SpanType
from agentguard.export import export_jsonl, export_otel_spans, trace_statistics


def _make_trace():
    trace = ExecutionTrace(task="export-test")
    a = Span(name="agent-1", span_type=SpanType.AGENT)
    t = Span(name="tool-1", span_type=SpanType.TOOL, parent_span_id=a.span_id)
    a.complete(output="done")
    t.complete(output="result")
    trace.add_span(a)
    trace.add_span(t)
    trace.complete()
    return trace


def test_export_jsonl():
    """JSONL export creates one line per span + header."""
    trace = _make_trace()
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        export_jsonl(trace, f.name)
        lines = Path(f.name).read_text().strip().split("\n")
        assert len(lines) == 3  # 1 header + 2 spans
        header = json.loads(lines[0])
        assert header["type"] == "trace"


def test_export_otel():
    """OTel export produces proper span format."""
    trace = _make_trace()
    otel = export_otel_spans(trace)
    assert len(otel) == 2
    assert otel[0]["operationName"] == "agent:agent-1"
    assert otel[0]["attributes"]["gen_ai.operation.name"] == "invoke_agent"
    assert otel[1]["operationName"] == "tool:tool-1"


def test_trace_statistics():
    """trace_statistics computes correct metrics."""
    trace = _make_trace()
    stats = trace_statistics(trace)
    assert stats["total_spans"] == 2
    assert stats["agent_count"] == 1
    assert stats["tool_count"] == 1
    assert stats["error_count"] == 0
    assert stats["deepest_nesting"] == 1
