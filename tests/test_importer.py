"""Tests for trace importer."""

import pytest

from agentguard.core.trace import SpanStatus, SpanType
from agentguard.importer import import_generic, import_otel


def _otel_trace():
    """Sample OTel format trace."""
    return {
        "resourceSpans": [{
            "scopeSpans": [{
                "spans": [
                    {
                        "traceId": "abc123",
                        "spanId": "span001",
                        "name": "coordinator",
                        "startTimeUnixNano": 1712880000000000000,
                        "endTimeUnixNano": 1712880005000000000,
                        "status": {"code": 1},
                        "attributes": [
                            {"key": "agentguard.span_type", "value": {"stringValue": "agent"}},
                        ],
                    },
                    {
                        "traceId": "abc123",
                        "spanId": "span002",
                        "parentSpanId": "span001",
                        "name": "llm_call",
                        "startTimeUnixNano": 1712880001000000000,
                        "endTimeUnixNano": 1712880003000000000,
                        "status": {"code": 1},
                    },
                    {
                        "traceId": "abc123",
                        "spanId": "span003",
                        "parentSpanId": "span001",
                        "name": "tool_search",
                        "startTimeUnixNano": 1712880003000000000,
                        "endTimeUnixNano": 1712880004000000000,
                        "status": {"code": 2, "message": "Connection refused"},
                    },
                ],
            }],
        }],
    }


class TestOtelImport:
    def test_basic(self):
        trace = import_otel(_otel_trace())
        assert len(trace.spans) == 3
        assert trace.spans[0].name == "coordinator"

    def test_span_types_guessed(self):
        trace = import_otel(_otel_trace())
        types = {s.name: s.span_type for s in trace.spans}
        assert types["coordinator"] == SpanType.AGENT
        assert types["llm_call"] == SpanType.LLM_CALL
        assert types["tool_search"] == SpanType.TOOL

    def test_failure_detected(self):
        trace = import_otel(_otel_trace())
        failed = [s for s in trace.spans if s.status == SpanStatus.FAILED]
        assert len(failed) == 1
        assert failed[0].error == "Connection refused"

    def test_parent_child(self):
        trace = import_otel(_otel_trace())
        child = next(s for s in trace.spans if s.name == "llm_call")
        assert child.parent_span_id is not None

    def test_timestamps(self):
        trace = import_otel(_otel_trace())
        assert trace.started_at
        assert trace.ended_at
        for s in trace.spans:
            assert s.started_at
            assert s.ended_at


class TestGenericImport:
    def test_agentguard_format(self):
        from agentguard.core.trace import ExecutionTrace, Span
        t = ExecutionTrace(task="native")
        t.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        data = t.to_dict()

        imported = import_generic(data)
        assert imported.task == "native"

    def test_otel_format(self):
        imported = import_generic(_otel_trace())
        assert len(imported.spans) == 3

    def test_unknown_format(self):
        with pytest.raises(ValueError):
            import_generic({"random": "data"})
