"""Tests for trace compression."""

import pytest
import json
from agentguard.builder import TraceBuilder
from agentguard.compress import compress_trace, measure_compression
from agentguard.core.trace import ExecutionTrace


class TestCompress:
    def test_light(self):
        trace = (TraceBuilder("compress_test")
            .agent("a", duration_ms=1000, output_data={"result": "data"})
                .tool("t1", duration_ms=500)
            .end()
            .build())
        
        compressed = compress_trace(trace, "light")
        original = trace.to_dict()
        
        # Compressed should be smaller (fewer keys)
        assert len(json.dumps(compressed)) <= len(json.dumps(original))

    def test_aggressive(self):
        trace = (TraceBuilder("aggressive_test")
            .agent("a", output_data={"large": "x" * 1000, "data": [1, 2, 3]})
            .end()
            .build())
        
        compressed = compress_trace(trace, "aggressive")
        # Output data should be replaced with keys only
        span = compressed["spans"][0]
        if "output_data" in span:
            assert "_keys" in span["output_data"]

    def test_measure(self):
        trace = (TraceBuilder("measure_test")
            .agent("a", duration_ms=2000, output_data={"big": "x" * 500})
                .tool("t1", duration_ms=1000)
            .end()
            .build())
        
        results = measure_compression(trace)
        assert "light" in results
        assert "aggressive" in results
        assert results["light"]["savings_pct"] >= 0
        assert results["aggressive"]["savings_pct"] >= results["light"]["savings_pct"]

    def test_empty_trace(self):
        trace = ExecutionTrace(task="empty")
        compressed = compress_trace(trace, "standard")
        assert compressed["spans"] == []
