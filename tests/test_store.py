"""Tests for trace store."""


import pytest

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus
from agentguard.store import TraceStore


@pytest.fixture
def store(tmp_path):
    return TraceStore(directory=str(tmp_path / "traces"))


class TestTraceStore:
    def test_save_and_load(self, store):
        trace = ExecutionTrace(trace_id="test-1", task="hello")
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        store.save(trace)

        loaded = store.load("test-1")
        assert loaded is not None
        assert loaded.task == "hello"
        assert len(loaded.spans) == 1

    def test_list(self, store):
        for i in range(5):
            t = ExecutionTrace(trace_id=f"trace-{i}", task=f"task_{i}", status=SpanStatus.COMPLETED)
            store.save(t)

        infos = store.list_traces()
        assert len(infos) == 5

    def test_query_by_status(self, store):
        t1 = ExecutionTrace(trace_id="good", task="ok", status=SpanStatus.COMPLETED)
        t2 = ExecutionTrace(trace_id="bad", task="fail", status=SpanStatus.FAILED)
        store.save(t1)
        store.save(t2)

        results = store.query(status="failed")
        assert len(results) == 1
        assert results[0].trace_id == "bad"

    def test_query_by_task(self, store):
        t1 = ExecutionTrace(trace_id="a", task="content pipeline")
        t2 = ExecutionTrace(trace_id="b", task="code review")
        store.save(t1)
        store.save(t2)

        results = store.query(task_contains="content")
        assert len(results) == 1

    def test_prune(self, store):
        for i in range(10):
            store.save(ExecutionTrace(trace_id=f"t-{i}"))

        assert store.count == 10
        removed = store.prune(keep=3)
        assert removed == 7
        assert store.count == 3

    def test_load_nonexistent(self, store):
        result = store.load("nonexistent")
        assert result is None

    def test_count(self, store):
        assert store.count == 0
        store.save(ExecutionTrace(trace_id="t1"))
        assert store.count == 1
