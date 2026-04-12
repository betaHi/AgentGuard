"""Tests for trace schema validation."""

import pytest
import json
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.schema import validate_trace_dict, validate_trace_json, get_schema


class TestValidateTraceDict:
    def test_valid_trace(self):
        trace = ExecutionTrace(task="test")
        trace.add_span(Span(name="a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED))
        errors = validate_trace_dict(trace.to_dict())
        assert errors == []

    def test_missing_trace_id(self):
        errors = validate_trace_dict({"status": "completed", "spans": []})
        assert any("trace_id" in e for e in errors)

    def test_missing_status(self):
        errors = validate_trace_dict({"trace_id": "x", "spans": []})
        assert any("status" in e for e in errors)

    def test_invalid_status(self):
        errors = validate_trace_dict({"trace_id": "x", "status": "invalid", "spans": []})
        assert any("status" in e.lower() for e in errors)

    def test_missing_span_fields(self):
        errors = validate_trace_dict({
            "trace_id": "x", "status": "completed",
            "spans": [{"name": "a"}]  # missing span_id, span_type, status
        })
        assert len(errors) >= 2

    def test_duplicate_span_ids(self):
        errors = validate_trace_dict({
            "trace_id": "x", "status": "completed",
            "spans": [
                {"span_id": "dup", "span_type": "agent", "name": "a", "status": "completed"},
                {"span_id": "dup", "span_type": "agent", "name": "b", "status": "completed"},
            ]
        })
        assert any("duplicate" in e for e in errors)

    def test_invalid_span_type(self):
        errors = validate_trace_dict({
            "trace_id": "x", "status": "completed",
            "spans": [{"span_id": "s1", "span_type": "invalid_type", "name": "a", "status": "completed"}]
        })
        assert any("span_type" in e for e in errors)

    def test_orphan_parent_ref(self):
        errors = validate_trace_dict({
            "trace_id": "x", "status": "completed",
            "spans": [{"span_id": "s1", "span_type": "agent", "name": "a", "status": "completed",
                       "parent_span_id": "nonexistent"}]
        })
        assert any("parent_span_id" in e for e in errors)


class TestValidateTraceJson:
    def test_valid_json(self):
        trace = ExecutionTrace(task="test")
        trace.add_span(Span(name="a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED))
        errors = validate_trace_json(trace.to_json())
        assert errors == []

    def test_invalid_json(self):
        errors = validate_trace_json("not json at all")
        assert any("JSON" in e for e in errors)


class TestGetSchema:
    def test_schema_returned(self):
        schema = get_schema()
        assert "title" in schema
        assert schema["version"] == "0.1.0"
        assert "properties" in schema
