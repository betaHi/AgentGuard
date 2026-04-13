"""Tests for trace size limits and truncation."""

import json
import logging
import pytest

from agentguard.core.limits import (
    check_trace_size, truncate_trace, _truncate_field,
    TRACE_WARN_BYTES, SPAN_DATA_MAX_BYTES, TRUNCATION_MARKER,
)
from agentguard.builder import TraceBuilder


def _small_trace_dict():
    trace = TraceBuilder("small").agent("a", duration_ms=100).end().build()
    return trace.to_dict()


def _large_trace_dict(size_mb=12):
    """Create a trace dict with oversized metadata."""
    d = _small_trace_dict()
    big_data = "x" * (size_mb * 1024 * 1024)
    d["spans"][0]["metadata"] = {"blob": big_data}
    return d


class TestCheckTraceSize:
    def test_small_trace_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            size = check_trace_size(_small_trace_dict())
        assert size < TRACE_WARN_BYTES
        assert "MB" not in caplog.text

    def test_large_trace_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            size = check_trace_size(_large_trace_dict())
        assert size > TRACE_WARN_BYTES
        assert "MB" in caplog.text

    def test_returns_size_in_bytes(self):
        size = check_trace_size(_small_trace_dict())
        assert isinstance(size, int)
        assert size > 0


class TestTruncateTrace:
    def test_small_trace_unchanged(self):
        d = _small_trace_dict()
        result = truncate_trace(d)
        assert result == d

    def test_large_metadata_truncated(self):
        d = _large_trace_dict()
        result = truncate_trace(d)
        result_json = json.dumps(result, default=str)
        assert len(result_json.encode()) < len(json.dumps(d, default=str).encode())
        assert TRUNCATION_MARKER in result_json

    def test_original_not_mutated(self):
        d = _large_trace_dict()
        original_size = len(json.dumps(d, default=str))
        truncate_trace(d)
        assert len(json.dumps(d, default=str)) == original_size

    def test_truncated_is_json_serializable(self):
        d = _large_trace_dict()
        result = truncate_trace(d)
        json.dumps(result)  # should not raise

    def test_span_fields_truncated(self):
        d = _small_trace_dict()
        big = "y" * (SPAN_DATA_MAX_BYTES + 1000)
        d["spans"][0]["input_data"] = big
        d["spans"][0]["output_data"] = big
        result = truncate_trace(d)
        for field in ("input_data", "output_data"):
            val = result["spans"][0][field]
            assert TRUNCATION_MARKER in val
            assert len(val.encode()) <= SPAN_DATA_MAX_BYTES + 100


class TestTruncateField:
    def test_small_field_unchanged(self):
        assert _truncate_field("hello", "test") == "hello"

    def test_none_unchanged(self):
        assert _truncate_field(None, "test") is None

    def test_large_string_truncated(self):
        big = "z" * (SPAN_DATA_MAX_BYTES + 5000)
        result = _truncate_field(big, "test")
        assert TRUNCATION_MARKER in result
        assert len(result.encode()) <= SPAN_DATA_MAX_BYTES + 100

    def test_large_dict_truncated(self):
        big = {"key": "v" * (SPAN_DATA_MAX_BYTES + 5000)}
        result = _truncate_field(big, "test")
        assert isinstance(result, dict)
        result_json = json.dumps(result, default=str)
        assert len(result_json.encode()) < SPAN_DATA_MAX_BYTES + 1000

    def test_large_list_truncated(self):
        big = ["item"] * (SPAN_DATA_MAX_BYTES // 2)
        result = _truncate_field(big, "test")
        assert isinstance(result, list)
        assert len(result) < len(big)


class TestToJsonIntegration:
    def test_to_json_truncate_flag(self):
        trace = TraceBuilder("big").agent("a", duration_ms=100).end().build()
        # Add oversized data directly
        trace.spans[0].metadata = {"blob": "x" * (SPAN_DATA_MAX_BYTES + 5000)}
        result = trace.to_json(truncate=True)
        assert TRUNCATION_MARKER in result

    def test_to_json_warns_on_large(self, caplog):
        trace = TraceBuilder("big").agent("a", duration_ms=100).end().build()
        trace.spans[0].metadata = {"blob": "x" * (12 * 1024 * 1024)}
        with caplog.at_level(logging.WARNING):
            trace.to_json()
        assert "MB" in caplog.text
