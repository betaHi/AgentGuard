"""Tests for trace correlation ID — linking traces across services."""

import json

from agentguard.core.trace import ExecutionTrace
from agentguard.sdk.recorder import TraceRecorder, set_correlation_id, set_parent_trace


class TestCorrelationId:
    def test_set_correlation_id(self):
        rec = TraceRecorder(task="test")
        rec.set_correlation_id("req-abc-123")
        assert rec.trace.correlation_id == "req-abc-123"

    def test_set_parent_trace(self):
        rec = TraceRecorder(task="child")
        rec.set_parent_trace("parent-trace-xyz")
        assert rec.trace.parent_trace_id == "parent-trace-xyz"

    def test_correlation_in_to_dict(self):
        t = ExecutionTrace(task="test", correlation_id="corr-1", parent_trace_id="parent-1")
        t.complete()
        d = t.to_dict()
        assert d["correlation_id"] == "corr-1"
        assert d["parent_trace_id"] == "parent-1"

    def test_correlation_in_json(self):
        t = ExecutionTrace(task="test", correlation_id="corr-2")
        t.complete()
        j = json.loads(t.to_json())
        assert j["correlation_id"] == "corr-2"

    def test_from_dict_round_trip(self):
        t = ExecutionTrace(task="test", correlation_id="corr-3", parent_trace_id="p-3")
        t.complete()
        t2 = ExecutionTrace.from_dict(t.to_dict())
        assert t2.correlation_id == "corr-3"
        assert t2.parent_trace_id == "p-3"

    def test_default_is_none(self):
        t = ExecutionTrace(task="test")
        assert t.correlation_id is None
        assert t.parent_trace_id is None

    def test_module_level_failopen(self):
        set_correlation_id("test-id")  # should not crash
        set_parent_trace("parent-id")

    def test_package_import(self):
        import agentguard
        assert hasattr(agentguard, 'set_correlation_id')
        assert hasattr(agentguard, 'set_parent_trace')
