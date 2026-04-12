"""Tests for enhanced trace export."""

import pytest
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.builder import TraceBuilder
from agentguard.export_v2 import trace_to_csv, traces_to_csv, trace_to_table


@pytest.fixture
def sample_trace():
    return (TraceBuilder("export_test")
        .agent("researcher", duration_ms=3000, token_count=1000, cost_usd=0.03)
            .tool("web_search", duration_ms=1000)
        .end()
        .handoff("researcher", "writer", context_size=500)
        .agent("writer", duration_ms=5000, status="failed", error="timeout")
        .end()
        .build())


class TestCSV:
    def test_basic(self, sample_trace):
        csv = trace_to_csv(sample_trace)
        lines = csv.split("\n")
        assert len(lines) >= 4  # header + 3+ spans
        assert "trace_id" in lines[0]

    def test_contains_data(self, sample_trace):
        csv = trace_to_csv(sample_trace)
        assert "researcher" in csv
        assert "writer" in csv
        assert "timeout" in csv

    def test_tsv(self, sample_trace):
        tsv = trace_to_csv(sample_trace, delimiter="\t")
        assert "\t" in tsv

    def test_escape_commas(self):
        trace = ExecutionTrace(task="escape")
        trace.add_span(Span(name="agent with, comma", error='error "with" quotes'))
        csv = trace_to_csv(trace)
        assert '"agent with, comma"' in csv

    def test_multi_trace(self, sample_trace):
        csv = traces_to_csv([sample_trace, sample_trace])
        lines = csv.split("\n")
        # 1 header + spans from 2 traces
        assert len(lines) > 5


class TestTable:
    def test_basic(self, sample_trace):
        rows = trace_to_table(sample_trace)
        assert len(rows) >= 3
        assert all("trace_id" in row for row in rows)
        assert all("name" in row for row in rows)

    def test_fields(self, sample_trace):
        rows = trace_to_table(sample_trace)
        researcher = next(r for r in rows if r["name"] == "researcher")
        assert researcher["token_count"] == 1000
        assert researcher["span_type"] == "agent"

    def test_handoff(self, sample_trace):
        rows = trace_to_table(sample_trace)
        handoff = next((r for r in rows if r["span_type"] == "handoff"), None)
        if handoff:
            assert handoff["handoff_from"] == "researcher"
            assert handoff["context_size_bytes"] == 500
